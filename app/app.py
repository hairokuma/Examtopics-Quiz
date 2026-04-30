from flask import Flask, render_template, request, jsonify, Response, stream_with_context
import sqlite3
import json
import logging
import os
import re
import time
import uuid
import threading
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin
import requests as http_client
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'data' / 'examtopics.db'

def get_db_connection():
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn

def _migrate_table(conn, table, columns):
    existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for col, definition in columns:
        if col not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            questions INTEGER,
            link TEXT,
            publisher TEXT,
            exam_name TEXT,
            created_at TEXT,
            updated_at TEXT,
            last_updated_on TEXT
        );

        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            topic_id INTEGER,
            question_id INTEGER,
            question_text TEXT,
            answer_object TEXT,
            correct_answer_keys TEXT,
            user_answer_keys TEXT,
            is_correct INTEGER,
            answered_at TEXT,
            is_marked INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            source_url TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );

        CREATE TABLE IF NOT EXISTS questions_scraped (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            topic_id INTEGER,
            question_id INTEGER,
            question_text TEXT,
            answer_object TEXT,
            correct_answer_keys TEXT,
            correct_answer_text TEXT,
            user_answer_keys TEXT,
            is_correct INTEGER DEFAULT 0,
            is_marked INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            source_url TEXT,
            FOREIGN KEY (project_id) REFERENCES projects (id)
        );

        CREATE TABLE IF NOT EXISTS discovered_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publisher TEXT NOT NULL,
            exam_name TEXT NOT NULL,
            url TEXT NOT NULL,
            scraped INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(url)
        );

        CREATE TABLE IF NOT EXISTS publishers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS scrape_jobs (
            id TEXT PRIMARY KEY,
            job_type TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running',
            publisher TEXT,
            project_id INTEGER,
            exam_name TEXT,
            total INTEGER DEFAULT 0,
            processed INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            fail_count INTEGER DEFAULT 0,
            log TEXT DEFAULT '[]',
            created_at TEXT,
            updated_at TEXT
        );
    ''')

    _migrate_table(conn, 'projects', [
        ('description', 'TEXT'),
        ('questions', 'INTEGER'),
        ('link', 'TEXT'),
        ('publisher', 'TEXT'),
        ('exam_name', 'TEXT'),
        ('last_updated_on', 'TEXT'),
    ])
    _migrate_table(conn, 'questions', [('source_url', 'TEXT')])

    conn.commit()
    conn.close()

init_db()

# ─── Scrape Job Helpers ──────────────────────────────────────────────────────

def _get_job(job_id):
    conn = get_db_connection()
    job = conn.execute('SELECT * FROM scrape_jobs WHERE id = ?', (job_id,)).fetchone()
    conn.close()
    if not job:
        return None
    d = dict(job)
    d['log'] = json.loads(d.get('log') or '[]')
    return d

def _create_job(job_id, job_type, publisher=None, project_id=None, exam_name=None):
    now = datetime.now().isoformat()
    conn = get_db_connection()
    conn.execute(
        'INSERT INTO scrape_jobs (id, job_type, status, publisher, project_id, exam_name, '
        'total, processed, success_count, fail_count, log, created_at, updated_at) '
        'VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0, ?, ?, ?)',
        (job_id, job_type, 'running', publisher, project_id, exam_name, '[]', now, now)
    )
    conn.commit()
    conn.close()

_VALID_JOB_COLUMNS = {'status', 'total', 'processed', 'success_count', 'fail_count'}

def _update_job(job_id, **kwargs):
    if not kwargs:
        return
    invalid = set(kwargs) - _VALID_JOB_COLUMNS
    if invalid:
        raise ValueError(f'Invalid job columns: {invalid}')
    now = datetime.now().isoformat()
    set_parts = [f'{k} = ?' for k in kwargs]
    set_parts.append('updated_at = ?')
    values = list(kwargs.values()) + [now, job_id]
    conn = get_db_connection()
    conn.execute(f'UPDATE scrape_jobs SET {", ".join(set_parts)} WHERE id = ?', values)
    conn.commit()
    conn.close()

def _log_job(job_id, message):
    conn = get_db_connection()
    job = conn.execute('SELECT log FROM scrape_jobs WHERE id = ?', (job_id,)).fetchone()
    if job:
        log = json.loads(job['log'] or '[]')
        log.append({'time': datetime.now().strftime('%H:%M:%S'), 'msg': message})
        if len(log) > 500:
            log = log[-500:]
        conn.execute(
            'UPDATE scrape_jobs SET log = ?, updated_at = ? WHERE id = ?',
            (json.dumps(log), datetime.now().isoformat(), job_id)
        )
        conn.commit()
    conn.close()

# ─── Scraping Logic ──────────────────────────────────────────────────────────

def _extract_urls_from_page(soup):
    urls = []
    seen = set()
    discussion_list = soup.find('div', class_='discussion-list')
    if discussion_list:
        for link in discussion_list.find_all('a', href=True):
            href = link['href']
            if '/discussions/' in href and '/view/' in href:
                full_url = urljoin('https://www.examtopics.com', href)
                if full_url not in seen:
                    seen.add(full_url)
                    urls.append(full_url)
    return urls

def _sort_urls_by_exam(urls):
    exam_urls = {}
    for url in urls:
        m = re.search(r'-exam-([a-z0-9-]+?)-topic-', url)
        if not m:
            m = re.search(r'-exam-([a-z0-9-]+)', url)
        exam_name = m.group(1) if m else 'unknown'
        exam_urls.setdefault(exam_name, []).append(url)

    def sort_key(url):
        m = re.search(r'-topic-(\d+)-question-(\d+)', url)
        return (int(m.group(1)), int(m.group(2))) if m else (999999, 999999)

    for exam in exam_urls:
        exam_urls[exam].sort(key=sort_key)

    return exam_urls

def _extract_text_with_images(element):
    if not element:
        return ''
    result = []
    for child in element.descendants:
        if child.name == 'img':
            src = child.get('src', '') or child.get('data-src', '')
            if src:
                if src.startswith('/'):
                    src = 'https://www.examtopics.com' + src
                result.append(f' {src} ')
        elif child.name == 'br':
            result.append('\n')
        elif isinstance(child, str):
            text = child.strip()
            if text:
                result.append(text)
    return ' '.join(result).strip()

def _scrape_question(url, session, project_id):
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        question_body = soup.find('div', class_='question-body')
        if not question_body:
            return None

        question_text = _extract_text_with_images(question_body.find('p', class_='card-text'))
        answers = {}
        correct_keys = []

        choices = question_body.find('div', class_='question-choices-container')
        if choices:
            for item in choices.find_all('li', class_='multi-choice-item'):
                letter_span = item.find('span', class_='multi-choice-letter')
                if letter_span:
                    letter = letter_span.get('data-choice-letter', '')
                    letter_span.extract()
                    answer_text = _extract_text_with_images(item).strip()
                    if letter and answer_text:
                        answers[letter] = answer_text
                    if 'correct-hidden' in item.get('class', []):
                        correct_keys.append(letter)

        answer_section = question_body.find('div', class_='question-answer')
        if answer_section:
            correct_span = answer_section.find('span', class_='correct-answer')
            if correct_span:
                img = correct_span.find('img')
                if img:
                    src = img.get('src', '') or img.get('data-src', '')
                    if src:
                        if src.startswith('/'):
                            src = 'https://www.examtopics.com' + src
                        answers['A'] = src
                        correct_keys = ['A']
                elif not correct_keys:
                    suggested = correct_span.get_text(strip=True)
                    correct_keys = [c for c in suggested.upper() if c.isalpha()]

        header = soup.find('div', class_='question-discussion-header')
        question_id = topic_id = None
        if header:
            m = re.search(r'Question\s*#:\s*(\d+)', header.get_text())
            if m:
                question_id = int(m.group(1))
            m = re.search(r'Topic\s*#:\s*(\d+)', header.get_text())
            if m:
                topic_id = int(m.group(1))

        correct_text = ', '.join([f"{k}. {answers.get(k, '')}" for k in correct_keys])
        now = datetime.now().isoformat()

        return {
            'project_id': project_id,
            'topic_id': topic_id,
            'question_id': question_id,
            'question_text': question_text,
            'answer_object': json.dumps(answers),
            'correct_answer_keys': json.dumps(correct_keys),
            'correct_answer_text': correct_text,
            'user_answer_keys': json.dumps([]),
            'is_correct': 0,
            'is_marked': 0,
            'created_at': now,
            'updated_at': now,
            'source_url': url,
        }
    except Exception:
        return None

def _save_scraped_question(data):
    conn = get_db_connection()
    existing = conn.execute(
        'SELECT id FROM questions_scraped WHERE project_id = ? AND source_url = ?',
        (data['project_id'], data['source_url'])
    ).fetchone()

    if existing:
        conn.execute('''
            UPDATE questions_scraped
            SET topic_id=?, question_id=?, question_text=?, answer_object=?,
                correct_answer_keys=?, correct_answer_text=?, updated_at=?
            WHERE id=?
        ''', (data['topic_id'], data['question_id'], data['question_text'],
              data['answer_object'], data['correct_answer_keys'],
              data['correct_answer_text'], data['updated_at'], existing['id']))
    else:
        conn.execute('''
            INSERT INTO questions_scraped
            (project_id, topic_id, question_id, question_text, answer_object,
             correct_answer_keys, correct_answer_text, user_answer_keys, is_correct,
             is_marked, created_at, updated_at, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['project_id'], data['topic_id'], data['question_id'],
              data['question_text'], data['answer_object'], data['correct_answer_keys'],
              data['correct_answer_text'], data['user_answer_keys'], data['is_correct'],
              data['is_marked'], data['created_at'], data['updated_at'], data['source_url']))

    conn.commit()
    conn.close()

# ─── Background Job Runners ──────────────────────────────────────────────────

def _run_discover_urls(job_id, publisher, delay):
    try:
        session = http_client.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

        base_url = f'https://www.examtopics.com/discussions/{publisher}/'
        _log_job(job_id, f'Fetching {base_url}1/ ...')

        resp = session.get(f'{base_url}1/', timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        total_pages = 1
        pagination = soup.find('span', class_='discussion-list-page-indicator')
        if pagination:
            m = re.search(r'of\s+<strong>(\d+)</strong>', str(pagination))
            if m:
                total_pages = int(m.group(1))

        _update_job(job_id, total=total_pages)
        _log_job(job_id, f'Found {total_pages} pages to scrape')

        all_urls = []

        for page_num in range(1, total_pages + 1):
            if page_num > 1:
                time.sleep(delay)
                try:
                    resp = session.get(f'{base_url}{page_num}/', timeout=30)
                    resp.raise_for_status()
                    soup = BeautifulSoup(resp.text, 'html.parser')
                except Exception as e:
                    _log_job(job_id, f'Page {page_num} error: {e}')
                    _update_job(job_id, processed=page_num)
                    continue

            page_urls = _extract_urls_from_page(soup)
            all_urls.extend(page_urls)
            _update_job(job_id, processed=page_num)
            _log_job(job_id, f'Page {page_num}/{total_pages}: {len(page_urls)} URLs (total: {len(all_urls)})')

        exam_urls = _sort_urls_by_exam(all_urls)
        _log_job(job_id, f'Sorted into {len(exam_urls)} exams. Saving...')

        conn = get_db_connection()
        all_new_urls = set()
        for exam_name, urls in exam_urls.items():
            for url in urls:
                conn.execute(
                    'INSERT OR IGNORE INTO discovered_urls (publisher, exam_name, url) VALUES (?, ?, ?)',
                    (publisher, exam_name, url)
                )
                all_new_urls.add(url)
        conn.commit()

        if all_new_urls:
            placeholders = ','.join('?' * len(all_new_urls))
            conn.execute(
                f'DELETE FROM discovered_urls WHERE publisher = ? AND url NOT IN ({placeholders})',
                [publisher] + list(all_new_urls)
            )
        else:
            conn.execute('DELETE FROM discovered_urls WHERE publisher = ?', (publisher,))
        conn.commit()
        conn.close()

        _update_job(job_id, status='completed', success_count=len(all_urls))
        _log_job(job_id, f'Done! {len(all_urls)} URLs across {len(exam_urls)} exams')

    except Exception as e:
        _update_job(job_id, status='failed')
        _log_job(job_id, f'Fatal error: {e}')


def _run_scrape_questions(job_id, project_id, exam_name, publisher, delay):
    try:
        conn = get_db_connection()
        urls = [row['url'] for row in conn.execute(
            'SELECT url FROM discovered_urls WHERE publisher = ? AND exam_name = ? ORDER BY id',
            (publisher, exam_name)
        ).fetchall()]
        conn.close()

        _update_job(job_id, total=len(urls))
        _log_job(job_id, f'Scraping {len(urls)} questions for {exam_name}...')

        session = http_client.Session()
        session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'})

        success = fail = 0

        for i, url in enumerate(urls):
            data = _scrape_question(url, session, project_id)
            if data:
                _save_scraped_question(data)
                success += 1
                conn = get_db_connection()
                conn.execute('UPDATE discovered_urls SET scraped = 1 WHERE url = ?', (url,))
                conn.commit()
                conn.close()
            else:
                fail += 1

            _update_job(job_id, processed=i + 1, success_count=success, fail_count=fail)

            if i == 0 or (i + 1) % 25 == 0 or i + 1 == len(urls):
                _log_job(job_id, f'{i+1}/{len(urls)}: {success} scraped, {fail} failed')

            time.sleep(delay)

        # Update project question count from scraped staging table
        conn = get_db_connection()
        count = conn.execute(
            'SELECT COUNT(*) FROM questions_scraped WHERE project_id = ?', (project_id,)
        ).fetchone()[0]
        conn.execute(
            'UPDATE projects SET questions = ?, updated_at = ? WHERE id = ?',
            (count, datetime.now().isoformat(), project_id)
        )
        conn.commit()
        conn.close()

        _update_job(job_id, status='completed')
        _log_job(job_id, f'Done! {success} scraped, {fail} failed. Project has {count} staged questions.')

    except Exception as e:
        _update_job(job_id, status='failed')
        _log_job(job_id, f'Fatal error: {e}')

# ─── Quiz Routes ─────────────────────────────────────────────────────────────

@app.route('/')
def index():
    conn = get_db_connection()
    projects = conn.execute('SELECT * FROM projects ORDER BY name').fetchall()

    projects_with_counts = []
    for project in projects:
        count = conn.execute(
            'SELECT COUNT(*) as count FROM questions WHERE project_id = ?',
            (project['id'],)
        ).fetchone()

        answered_count = conn.execute(
            'SELECT COUNT(*) as count FROM questions WHERE project_id = ? AND answered_at IS NOT NULL',
            (project['id'],)
        ).fetchone()

        project_dict = dict(project)
        project_dict['question_count'] = count['count']
        project_dict['progress'] = answered_count['count']
        projects_with_counts.append(project_dict)

    conn.close()
    projects_with_counts.sort(key=lambda p: (0 if p['question_count'] > 0 else 1, p['name']))
    return render_template('index.html', projects=projects_with_counts)

@app.route('/search')
@app.route('/search/<int:project_id>')
def search(project_id=None):
    project = None
    if project_id:
        conn = get_db_connection()
        project = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
        conn.close()
        if not project:
            return "Project not found", 404
    return render_template('search.html', project=project)

@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip()
    project_id = request.args.get('project_id', type=int)
    exclude_case_study = request.args.get('exclude_case_study', 'false').lower() == 'true'

    if len(query) < 3:
        return jsonify([])

    conn = get_db_connection()

    if query.startswith('"') and query.endswith('"'):
        search_phrase = query[1:-1].strip()
        if len(search_phrase) < 2:
            conn.close()
            return jsonify([])

        search_pattern = f'%{search_phrase}%'
        case_study_filter = "AND LOWER(q.question_text) NOT LIKE '%case study%'" if exclude_case_study else ""
        if project_id:
            sql = f'''
                SELECT q.*, p.name as project_name, p.id as project_id,
                    ((LENGTH(q.question_text) - LENGTH(REPLACE(LOWER(q.question_text), LOWER(?), ''))) / LENGTH(?) +
                     (LENGTH(q.answer_object) - LENGTH(REPLACE(LOWER(q.answer_object), LOWER(?), ''))) / LENGTH(?)) as relevance_score
                FROM questions q
                JOIN projects p ON q.project_id = p.id
                WHERE q.project_id = ? AND (q.question_text LIKE ? OR q.answer_object LIKE ?) {case_study_filter}
                ORDER BY relevance_score DESC, q.topic_id, q.question_id
                LIMIT 100
            '''
            questions = conn.execute(sql, [search_phrase, search_phrase, search_phrase, search_phrase, project_id, search_pattern, search_pattern]).fetchall()
        else:
            sql = f'''
                SELECT q.*, p.name as project_name, p.id as project_id,
                    ((LENGTH(q.question_text) - LENGTH(REPLACE(LOWER(q.question_text), LOWER(?), ''))) / LENGTH(?) +
                     (LENGTH(q.answer_object) - LENGTH(REPLACE(LOWER(q.answer_object), LOWER(?), ''))) / LENGTH(?)) as relevance_score
                FROM questions q
                JOIN projects p ON q.project_id = p.id
                WHERE (q.question_text LIKE ? OR q.answer_object LIKE ?) {case_study_filter}
                ORDER BY relevance_score DESC, q.project_id, q.topic_id, q.question_id
                LIMIT 100
            '''
            questions = conn.execute(sql, [search_phrase, search_phrase, search_phrase, search_phrase, search_pattern, search_pattern]).fetchall()
    else:
        words = query.split()
        where_clauses = []
        params = []

        for word in words:
            if len(word) >= 2:
                search_pattern = f'%{word}%'
                where_clauses.append('(q.question_text LIKE ? OR q.answer_object LIKE ?)')
                params.extend([search_pattern, search_pattern])

        if not where_clauses:
            conn.close()
            return jsonify([])

        where_clause = ' AND '.join(where_clauses)
        relevance_parts = []
        relevance_params = []
        for word in words:
            if len(word) >= 2:
                relevance_parts.append(
                    '((LENGTH(q.question_text) - LENGTH(REPLACE(LOWER(q.question_text), LOWER(?), \'\'))) / LENGTH(?) + '
                    '(LENGTH(q.answer_object) - LENGTH(REPLACE(LOWER(q.answer_object), LOWER(?), \'\'))) / LENGTH(?))'
                )
                relevance_params.extend([word, word, word, word])

        relevance_score = ' + '.join(relevance_parts) if relevance_parts else '0'
        case_study_filter = "AND LOWER(q.question_text) NOT LIKE '%case study%'" if exclude_case_study else ""

        if project_id:
            sql = f'''
                SELECT q.*, p.name as project_name, p.id as project_id,
                    ({relevance_score}) as relevance_score
                FROM questions q
                JOIN projects p ON q.project_id = p.id
                WHERE q.project_id = ? AND ({where_clause}) {case_study_filter}
                ORDER BY relevance_score DESC, q.topic_id, q.question_id
                LIMIT 100
            '''
            questions = conn.execute(sql, relevance_params + [project_id] + params).fetchall()
        else:
            sql = f'''
                SELECT q.*, p.name as project_name, p.id as project_id,
                    ({relevance_score}) as relevance_score
                FROM questions q
                JOIN projects p ON q.project_id = p.id
                WHERE ({where_clause}) {case_study_filter}
                ORDER BY relevance_score DESC, q.project_id, q.topic_id, q.question_id
                LIMIT 100
            '''
            questions = conn.execute(sql, relevance_params + params).fetchall()

    conn.close()

    results = []
    for q in questions:
        answers = json.loads(q['answer_object'])
        correct_keys = json.loads(q['correct_answer_keys'])

        correct_answers_text = []
        for key in sorted(correct_keys):
            if key in answers:
                correct_answers_text.append(f"{key}. {answers[key]}")

        answers_text = []
        for key in sorted(answers.keys()):
            answers_text.append(f"{key}. {answers[key]}")

        results.append({
            'id': q['id'],
            'project_id': q['project_id'],
            'project_name': q['project_name'],
            'topic_id': q['topic_id'],
            'question_id': q['question_id'],
            'question_text': q['question_text'],
            'answers': answers,
            'answers_text': answers_text,
            'correct_answer_keys': correct_keys,
            'correct_answers_text': correct_answers_text
        })

    return jsonify(results)

@app.route('/quiz/<int:project_id>')
@app.route('/quiz/<int:project_id>/question/<int:question_number>')
def quiz(project_id, question_number=None):
    conn = get_db_connection()
    project = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    conn.close()
    if not project:
        return "Project not found", 404
    return render_template('quiz.html', project=project)

@app.route('/api/questions/<int:project_id>')
def get_questions(project_id):
    conn = get_db_connection()
    questions = conn.execute('''
        SELECT * FROM questions WHERE project_id = ? ORDER BY topic_id, question_id
    ''', (project_id,)).fetchall()
    conn.close()
    return jsonify([
        {
            **dict(q),
            'answers': json.loads(q['answer_object']),
            'correct_answer_keys': json.loads(q['correct_answer_keys'])
        }
        for q in questions
    ])

@app.route('/api/submit_answer', methods=['POST'])
def submit_answer():
    data = request.json
    if not data or 'question_id' not in data or 'user_answers' not in data:
        return jsonify({'error': 'question_id and user_answers are required'}), 400
    if not isinstance(data['question_id'], int) or not isinstance(data['user_answers'], list):
        return jsonify({'error': 'Invalid types for question_id or user_answers'}), 400
    question_id = data['question_id']
    user_answers = sorted(data['user_answers'])

    conn = get_db_connection()
    question = conn.execute(
        'SELECT correct_answer_keys FROM questions WHERE id = ?', (question_id,)
    ).fetchone()

    if not question:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404

    correct_answers = sorted(json.loads(question['correct_answer_keys']))
    is_correct = user_answers == correct_answers

    conn.execute('''
        UPDATE questions
        SET user_answer_keys = ?, is_correct = ?, answered_at = ?, updated_at = ?
        WHERE id = ?
    ''', (json.dumps(user_answers), 1 if is_correct else 0,
          datetime.now().isoformat(), datetime.now().isoformat(), question_id))
    conn.commit()
    conn.close()

    return jsonify({'correct': is_correct, 'correct_answers': correct_answers, 'user_answers': user_answers})

@app.route('/api/toggle_mark/<int:question_id>', methods=['POST'])
def toggle_mark(question_id):
    conn = get_db_connection()
    question = conn.execute('SELECT is_marked FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404

    new_status = 0 if question['is_marked'] else 1
    conn.execute('UPDATE questions SET is_marked = ?, updated_at = ? WHERE id = ?',
                 (new_status, datetime.now().isoformat(), question_id))
    conn.commit()
    conn.close()
    return jsonify({'is_marked': new_status})

@app.route('/api/stats/<int:project_id>')
def get_stats(project_id):
    conn = get_db_connection()
    stats = conn.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN answered_at IS NOT NULL THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN is_marked = 1 THEN 1 ELSE 0 END) as marked
        FROM questions WHERE project_id = ?
    ''', (project_id,)).fetchone()
    conn.close()
    return jsonify({
        'total': stats['total'],
        'answered': stats['answered'],
        'correct': stats['correct'],
        'marked': stats['marked']
    })

@app.route('/api/reset_progress/<int:project_id>', methods=['POST'])
def reset_progress(project_id):
    conn = get_db_connection()
    project = conn.execute('SELECT id FROM projects WHERE id = ?', (project_id,)).fetchone()
    if not project:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404

    conn.execute('''
        UPDATE questions
        SET user_answer_keys = NULL, is_correct = NULL, answered_at = NULL,
            is_marked = 0, updated_at = ?
        WHERE project_id = ?
    ''', (datetime.now().isoformat(), project_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'message': 'Progress reset successfully'})

# ─── Scraper Routes ───────────────────────────────────────────────────────────

@app.route('/scraper')
def scraper_page():
    return render_template('scraper.html')

@app.route('/api/scraper/publishers', methods=['GET'])
def get_publishers():
    conn = get_db_connection()
    rows = conn.execute('SELECT name FROM publishers ORDER BY name').fetchall()
    result = []
    for row in rows:
        p = row['name']
        stats = conn.execute(
            'SELECT COUNT(*) as cnt, MAX(created_at) as last_at FROM discovered_urls WHERE publisher = ?',
            (p,)
        ).fetchone()
        exams = conn.execute(
            'SELECT COUNT(DISTINCT exam_name) as cnt FROM discovered_urls WHERE publisher = ?', (p,)
        ).fetchone()
        result.append({
            'name': p,
            'url_count': stats['cnt'],
            'exam_count': exams['cnt'],
            'last_discovered_at': stats['last_at'],
        })
    conn.close()
    return jsonify(result)

@app.route('/api/scraper/publishers', methods=['POST'])
def add_publisher():
    name = (request.json or {}).get('name', '').strip().lower()
    if not name:
        return jsonify({'error': 'name required'}), 400
    conn = get_db_connection()
    conn.execute('INSERT OR IGNORE INTO publishers (name) VALUES (?)', (name,))
    conn.commit()
    conn.close()
    return jsonify({'name': name})

@app.route('/api/scraper/start_discovery', methods=['POST'])
def start_discovery():
    data = request.json
    publisher = data.get('publisher', '').strip()
    delay = float(data.get('delay', 1.5))
    if not publisher:
        return jsonify({'error': 'publisher required'}), 400

    job_id = str(uuid.uuid4())
    _create_job(job_id, 'url_discovery', publisher=publisher)
    threading.Thread(target=_run_discover_urls, args=(job_id, publisher, delay), daemon=True).start()
    return jsonify({'job_id': job_id})

@app.route('/api/scraper/exams/<publisher>')
def get_exams(publisher):
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT exam_name, COUNT(*) as url_count, SUM(scraped) as scraped_url_count
        FROM discovered_urls WHERE publisher = ?
        GROUP BY exam_name ORDER BY exam_name
    ''', (publisher,)).fetchall()

    exams = []
    for row in rows:
        project = conn.execute(
            'SELECT id, name FROM projects WHERE publisher = ? AND exam_name = ?',
            (publisher, row['exam_name'])
        ).fetchone()

        scraped_q = 0
        imported_q = 0
        if project:
            scraped_q = conn.execute(
                'SELECT COUNT(*) FROM questions_scraped WHERE project_id = ?', (project['id'],)
            ).fetchone()[0]
            imported_q = conn.execute(
                'SELECT COUNT(*) FROM questions WHERE project_id = ?', (project['id'],)
            ).fetchone()[0]

        exams.append({
            'exam_name': row['exam_name'],
            'url_count': row['url_count'],
            'scraped_url_count': row['scraped_url_count'] or 0,
            'project_id': project['id'] if project else None,
            'project_name': project['name'] if project else None,
            'scraped_question_count': scraped_q,
            'imported_question_count': imported_q,
        })
    conn.close()
    return jsonify(exams)

@app.route('/api/scraper/fetch_project_info', methods=['POST'])
def fetch_project_info():
    link = request.json.get('link', '').strip()
    if not link:
        return jsonify({'error': 'link required'}), 400

    try:
        resp = http_client.get(link, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')

        question_count = None
        last_updated = None
        description = ''

        for item in soup.find_all('div', class_='examQa__footer-info-item'):
            marked = item.find_all(class_='marked')
            if len(marked) >= 2:
                try:
                    question_count = int(marked[1].get_text(strip=True).replace(',', ''))
                except (ValueError, AttributeError):
                    pass

        date_elem = soup.find(class_='examQa__date')
        if date_elem:
            last_updated = date_elem.get_text(strip=True).replace('Last Updated on', '').strip()

        desc_elem = soup.find('meta', {'name': 'description'})
        if desc_elem:
            description = desc_elem.get('content', '')

        return jsonify({'question_count': question_count, 'last_updated': last_updated, 'description': description})
    except Exception:
        logger.exception('fetch_project_info failed for %s', link)
        return jsonify({'error': 'Failed to fetch project info'}), 500

@app.route('/api/scraper/create_project', methods=['POST'])
def create_project():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400

    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO projects (name, description, questions, link, publisher, exam_name,
                              last_updated_on, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, data.get('description', ''), data.get('questions'),
          data.get('link', ''), data.get('publisher', ''), data.get('exam_name', ''),
          data.get('last_updated_on', ''), now, now))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': project_id, 'name': name})

@app.route('/api/scraper/start_scrape', methods=['POST'])
def start_scrape():
    data = request.json
    project_id = data.get('project_id')
    exam_name = data.get('exam_name', '').strip()
    publisher = data.get('publisher', '').strip()
    delay = float(data.get('delay', 1.0))

    if not all([project_id, exam_name, publisher]):
        return jsonify({'error': 'project_id, exam_name, publisher required'}), 400

    job_id = str(uuid.uuid4())
    _create_job(job_id, 'question_scrape', publisher=publisher, project_id=project_id, exam_name=exam_name)
    threading.Thread(
        target=_run_scrape_questions,
        args=(job_id, project_id, exam_name, publisher, delay),
        daemon=True
    ).start()
    return jsonify({'job_id': job_id})

@app.route('/api/scraper/job/<job_id>')
def get_job_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/api/scraper/running_jobs')
def get_running_jobs():
    conn = get_db_connection()
    jobs = conn.execute(
        "SELECT id, job_type, publisher, exam_name, total, processed, success_count, fail_count "
        "FROM scrape_jobs WHERE status = 'running' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(j) for j in jobs])

@app.route('/api/scraper/stream/<job_id>')
def stream_job(job_id):
    def generate():
        last_log_idx = 0
        while True:
            job = _get_job(job_id)
            if not job:
                yield f'data: {json.dumps({"error": "not found"})}\n\n'
                break

            log = job.get('log', [])
            new_log = log[last_log_idx:]
            last_log_idx = len(log)

            yield f'data: {json.dumps({"status": job["status"], "total": job["total"], "processed": job["processed"], "success_count": job["success_count"], "fail_count": job["fail_count"], "new_log": new_log})}\n\n'

            if job['status'] in ('completed', 'failed'):
                break
            time.sleep(1)

    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
    )

@app.route('/api/scraper/import/<int:project_id>', methods=['POST'])
def import_questions(project_id):
    conn = get_db_connection()
    if not conn.execute('SELECT id FROM projects WHERE id = ?', (project_id,)).fetchone():
        conn.close()
        return jsonify({'error': 'Project not found'}), 404

    scraped = conn.execute(
        'SELECT * FROM questions_scraped WHERE project_id = ?', (project_id,)
    ).fetchall()

    imported = skipped = 0
    now = datetime.now().isoformat()

    for q in scraped:
        if conn.execute(
            'SELECT id FROM questions WHERE project_id = ? AND source_url = ?',
            (project_id, q['source_url'])
        ).fetchone():
            skipped += 1
        else:
            conn.execute('''
                INSERT INTO questions
                (project_id, topic_id, question_id, question_text, answer_object,
                 correct_answer_keys, is_marked, created_at, updated_at, source_url)
                VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
            ''', (q['project_id'], q['topic_id'], q['question_id'], q['question_text'],
                  q['answer_object'], q['correct_answer_keys'], now, now, q['source_url']))
            imported += 1

    conn.commit()
    conn.close()
    return jsonify({'imported': imported, 'skipped': skipped})

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true', host='0.0.0.0', port=5000)
