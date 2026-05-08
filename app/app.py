from flask import Flask, render_template, request, jsonify, Response, stream_with_context
from functools import wraps
from logging.handlers import TimedRotatingFileHandler
from werkzeug.middleware.proxy_fix import ProxyFix
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
app.secret_key = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1)

BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR / 'data' / 'examtopics.db'

# ─── Access / Security Logging ───────────────────────────────────────────────

_SCANNER_PATHS = {
    '/build', '/backend', '/wordpress', '/wp-admin', '/wp-login',
    '/phpMyAdmin', '/phpmyadmin', '/shell', '/.env', '/.git',
    '/config', '/setup', '/install', '/xmlrpc.php', '/cgi-bin',
}

_access_logger = logging.getLogger('access')
_access_logger.setLevel(logging.INFO)
_access_handler = TimedRotatingFileHandler(
    str(BASE_DIR / 'data' / 'access.log'), when='D', interval=1, backupCount=30
)
_access_handler.setFormatter(logging.Formatter('%(message)s'))
_access_logger.addHandler(_access_handler)
_access_logger.propagate = False

def _get_client_ip():
    return request.remote_addr

@app.before_request
def log_request():
    ip = _get_client_ip()
    path = request.path
    is_scanner = any(path == p or path.startswith(p + '/') for p in _SCANNER_PATHS)
    entry = {
        'time': datetime.now().isoformat(),
        'ip': ip,
        'method': request.method,
        'path': path,
        'ua': request.headers.get('User-Agent', ''),
    }
    if is_scanner:
        entry['flag'] = 'SCANNER'
    _access_logger.log(
        logging.WARNING if is_scanner else logging.INFO,
        json.dumps(entry, separators=(',', ':'))
    )

def get_db_connection():
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn

def _migrate_table(conn, table, columns):
    existing = {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}
    for col, definition in columns:
        if col not in existing:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {definition}')

def _migrate_drop_publisher_from_projects(conn):
    cols = {row[1] for row in conn.execute('PRAGMA table_info(projects)').fetchall()}
    if 'publisher' not in cols:
        return
    sqlite_ver = tuple(int(x) for x in sqlite3.sqlite_version.split('.'))
    if sqlite_ver >= (3, 35, 0):
        conn.execute('ALTER TABLE projects DROP COLUMN publisher')
    else:
        conn.executescript('''
            CREATE TABLE projects_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL, description TEXT, questions INTEGER,
                link TEXT, exam_name TEXT, created_at TEXT, updated_at TEXT, last_updated_on TEXT
            );
            INSERT INTO projects_new
                SELECT id, name, description, questions, link, exam_name, created_at, updated_at, last_updated_on
                FROM projects;
            DROP TABLE projects;
            ALTER TABLE projects_new RENAME TO projects;
        ''')
    conn.commit()

def init_db():
    conn = get_db_connection()
    conn.executescript('''
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            questions INTEGER,
            link TEXT,
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
        ('exam_name', 'TEXT'),
        ('last_updated_on', 'TEXT'),
        ('publisher_id', 'INTEGER REFERENCES publishers(id)'),
    ])
    _migrate_drop_publisher_from_projects(conn)
    _migrate_table(conn, 'questions', [('source_url', 'TEXT')])

    conn.commit()
    conn.close()

init_db()

# ─── Security ────────────────────────────────────────────────────────────────

_SCRAPER_PASSWORD = os.environ.get('SCRAPER_PASSWORD', '')

def _require_scraper_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not _SCRAPER_PASSWORD:
            if os.environ.get('FLASK_ENV') == 'production':
                return jsonify({'error': 'Scraper access disabled — set SCRAPER_PASSWORD'}), 403
            return f(*args, **kwargs)
        auth = request.authorization
        if not auth or auth.password != _SCRAPER_PASSWORD:
            return Response(
                'Authentication required', 401,
                {'WWW-Authenticate': 'Basic realm="Scraper"'}
            )
        return f(*args, **kwargs)
    return decorated

@app.after_request
def set_security_headers(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

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
        m = re.search(r'-exam-([a-z0-9_-]+?)-topic-', url)
        if not m:
            m = re.search(r'-exam-([a-z0-9_-]+)', url)
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
        'SELECT id FROM questions WHERE project_id = ? AND source_url = ?',
        (data['project_id'], data['source_url'])
    ).fetchone()

    if existing:
        conn.execute('''
            UPDATE questions
            SET topic_id=?, question_id=?, question_text=?, answer_object=?,
                correct_answer_keys=?, updated_at=?
            WHERE id=?
        ''', (data['topic_id'], data['question_id'], data['question_text'],
              data['answer_object'], data['correct_answer_keys'],
              data['updated_at'], existing['id']))
    else:
        conn.execute('''
            INSERT INTO questions
            (project_id, topic_id, question_id, question_text, answer_object,
             correct_answer_keys, is_marked, created_at, updated_at, source_url)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?)
        ''', (data['project_id'], data['topic_id'], data['question_id'],
              data['question_text'], data['answer_object'], data['correct_answer_keys'],
              data['created_at'], data['updated_at'], data['source_url']))

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

        now = datetime.now().isoformat()
        conn = get_db_connection()
        count = conn.execute(
            'SELECT COUNT(*) FROM questions WHERE project_id = ?', (project_id,)
        ).fetchone()[0]
        pub = conn.execute('SELECT id FROM publishers WHERE name = ?', (publisher,)).fetchone()
        conn.execute(
            'UPDATE projects SET questions = ?, publisher_id = ?, updated_at = ? WHERE id = ?',
            (count, pub['id'] if pub else None, now, project_id)
        )
        conn.commit()
        conn.close()

        _update_job(job_id, status='completed')
        _log_job(job_id, f'Done! {success} scraped, {fail} failed. {count} total in quiz.')

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
    if len(data['user_answers']) > 10:
        return jsonify({'error': 'Too many answers'}), 400
    if not all(isinstance(a, str) and re.fullmatch(r'[A-Z]', a) for a in data['user_answers']):
        return jsonify({'error': 'Invalid answer keys'}), 400
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
@_require_scraper_auth
def scraper_page():
    return render_template('scraper.html')

@app.route('/api/scraper/publishers', methods=['GET'])
@_require_scraper_auth
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
@_require_scraper_auth
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
@_require_scraper_auth
def start_discovery():
    data = request.json or {}
    publisher = data.get('publisher', '').strip()
    if not publisher:
        return jsonify({'error': 'publisher required'}), 400
    if not re.fullmatch(r'[a-z0-9-]+', publisher):
        return jsonify({'error': 'Invalid publisher name'}), 400
    delay = max(0.5, min(float(data.get('delay', 1.5)), 10.0))

    conn = get_db_connection()
    running = conn.execute(
        "SELECT id FROM scrape_jobs WHERE job_type='url_discovery' AND publisher=? AND status='running'",
        (publisher,)
    ).fetchone()
    conn.close()
    if running:
        return jsonify({'error': 'A discovery job is already running for this publisher'}), 409

    job_id = str(uuid.uuid4())
    _create_job(job_id, 'url_discovery', publisher=publisher)
    threading.Thread(target=_run_discover_urls, args=(job_id, publisher, delay), daemon=True).start()
    return jsonify({'job_id': job_id})

@app.route('/api/scraper/exams/<publisher>')
@_require_scraper_auth
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
            'SELECT id, name FROM projects WHERE exam_name = ?',
            (row['exam_name'],)
        ).fetchone()

        imported_q = 0
        if project:
            imported_q = conn.execute(
                'SELECT COUNT(*) FROM questions WHERE project_id = ?', (project['id'],)
            ).fetchone()[0]

        exams.append({
            'exam_name': row['exam_name'],
            'url_count': row['url_count'],
            'scraped_url_count': row['scraped_url_count'] or 0,
            'project_id': project['id'] if project else None,
            'project_name': project['name'] if project else None,
            'imported_question_count': imported_q,
        })
    conn.close()
    return jsonify(exams)

@app.route('/api/scraper/fetch_project_info', methods=['POST'])
@_require_scraper_auth
def fetch_project_info():
    link = (request.json or {}).get('link', '').strip()
    if not link:
        return jsonify({'error': 'link required'}), 400
    if not link.startswith('https://www.examtopics.com/'):
        return jsonify({'error': 'Only examtopics.com URLs are allowed'}), 400

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
@_require_scraper_auth
def create_project():
    data = request.json
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400

    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO projects (name, description, questions, link, exam_name,
                              last_updated_on, publisher_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, data.get('description', ''), data.get('questions'),
          data.get('link', ''), data.get('exam_name', ''),
          data.get('last_updated_on', ''), data.get('publisher_id'), now, now))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': project_id, 'name': name})

@app.route('/api/scraper/start_scrape', methods=['POST'])
@_require_scraper_auth
def start_scrape():
    data = request.json or {}
    project_id = data.get('project_id')
    exam_name = data.get('exam_name', '').strip()
    publisher = data.get('publisher', '').strip()
    if not all([project_id, exam_name, publisher]):
        return jsonify({'error': 'project_id, exam_name, publisher required'}), 400
    delay = max(0.5, min(float(data.get('delay', 1.0)), 10.0))

    conn = get_db_connection()
    running = conn.execute(
        "SELECT id FROM scrape_jobs WHERE job_type='question_scrape' AND project_id=? AND status='running'",
        (project_id,)
    ).fetchone()
    conn.close()
    if running:
        return jsonify({'error': 'A scrape job is already running for this project'}), 409

    job_id = str(uuid.uuid4())
    _create_job(job_id, 'question_scrape', publisher=publisher, project_id=project_id, exam_name=exam_name)
    threading.Thread(
        target=_run_scrape_questions,
        args=(job_id, project_id, exam_name, publisher, delay),
        daemon=True
    ).start()
    return jsonify({'job_id': job_id})

@app.route('/api/scraper/job/<job_id>')
@_require_scraper_auth
def get_job_status(job_id):
    job = _get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)

@app.route('/api/scraper/running_jobs')
@_require_scraper_auth
def get_running_jobs():
    conn = get_db_connection()
    jobs = conn.execute(
        "SELECT id, job_type, publisher, exam_name, total, processed, success_count, fail_count "
        "FROM scrape_jobs WHERE status = 'running' ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return jsonify([dict(j) for j in jobs])

@app.route('/api/scraper/stream/<job_id>')
@_require_scraper_auth
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


# ─── Admin Routes ────────────────────────────────────────────────────────────

@app.route('/admin')
@_require_scraper_auth
def admin_page():
    return render_template('admin.html')

@app.route('/api/admin/projects')
@_require_scraper_auth
def admin_get_projects():
    conn = get_db_connection()
    projects = conn.execute('''
        SELECT p.*, COUNT(q.id) as question_count
        FROM projects p
        LEFT JOIN questions q ON q.project_id = p.id
        GROUP BY p.id
        ORDER BY p.name
    ''').fetchall()
    conn.close()
    return jsonify([dict(p) for p in projects])

@app.route('/api/admin/projects', methods=['POST'])
@_require_scraper_auth
def admin_create_project():
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO projects (name, description, questions, link, exam_name,
                              last_updated_on, publisher_id, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (name, data.get('description', ''), data.get('questions'),
          data.get('link', ''), data.get('exam_name', ''),
          data.get('last_updated_on', ''), data.get('publisher_id'), now, now))
    project_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': project_id, 'name': name})

@app.route('/api/admin/projects/<int:project_id>', methods=['PUT'])
@_require_scraper_auth
def admin_update_project(project_id):
    data = request.json or {}
    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'name required'}), 400
    now = datetime.now().isoformat()
    conn = get_db_connection()
    base = (name, data.get('description', ''), data.get('questions'),
            data.get('link', ''), data.get('exam_name', ''),
            data.get('last_updated_on', ''), now)
    if 'publisher_id' in data:
        conn.execute('''
            UPDATE projects SET name=?, description=?, questions=?, link=?, exam_name=?,
                last_updated_on=?, updated_at=?, publisher_id=?
            WHERE id=?
        ''', base + (data['publisher_id'], project_id))
    else:
        conn.execute('''
            UPDATE projects SET name=?, description=?, questions=?, link=?, exam_name=?,
                last_updated_on=?, updated_at=?
            WHERE id=?
        ''', base + (project_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/projects/<int:project_id>', methods=['DELETE'])
@_require_scraper_auth
def admin_delete_project(project_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM questions WHERE project_id = ?', (project_id,))
    conn.execute('DELETE FROM projects WHERE id = ?', (project_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/projects/<int:project_id>/questions')
@_require_scraper_auth
def admin_get_questions(project_id):
    conn = get_db_connection()
    questions = conn.execute('''
        SELECT id, topic_id, question_id, question_text, answer_object, correct_answer_keys, source_url
        FROM questions WHERE project_id = ? ORDER BY topic_id, question_id
    ''', (project_id,)).fetchall()
    conn.close()
    return jsonify([dict(q) for q in questions])

@app.route('/api/admin/projects/<int:project_id>/questions', methods=['POST'])
@_require_scraper_auth
def admin_create_question(project_id):
    data = request.json or {}
    try:
        answer_obj = json.loads(data.get('answer_object', '{}'))
        correct_keys = json.loads(data.get('correct_answer_keys', '[]'))
        if not isinstance(answer_obj, dict) or not isinstance(correct_keys, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return jsonify({'error': 'answer_object must be a JSON object, correct_answer_keys must be a JSON array'}), 400
    now = datetime.now().isoformat()
    conn = get_db_connection()
    cursor = conn.execute('''
        INSERT INTO questions (project_id, topic_id, question_id, question_text, answer_object,
            correct_answer_keys, user_answer_keys, is_correct, is_marked, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)
    ''', (project_id, data.get('topic_id'), data.get('question_id'),
          data.get('question_text', ''), json.dumps(answer_obj), json.dumps(correct_keys),
          json.dumps([]), now, now))
    question_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'id': question_id})

@app.route('/api/admin/questions/<int:question_id>', methods=['PUT'])
@_require_scraper_auth
def admin_update_question(question_id):
    data = request.json or {}
    try:
        answer_obj = json.loads(data.get('answer_object', '{}'))
        correct_keys = json.loads(data.get('correct_answer_keys', '[]'))
        if not isinstance(answer_obj, dict) or not isinstance(correct_keys, list):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return jsonify({'error': 'answer_object must be a JSON object, correct_answer_keys must be a JSON array'}), 400
    now = datetime.now().isoformat()
    conn = get_db_connection()
    conn.execute('''
        UPDATE questions SET topic_id=?, question_id=?, question_text=?, answer_object=?,
            correct_answer_keys=?, updated_at=?
        WHERE id=?
    ''', (data.get('topic_id'), data.get('question_id'), data.get('question_text', ''),
          json.dumps(answer_obj), json.dumps(correct_keys), now, question_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/questions/<int:question_id>', methods=['DELETE'])
@_require_scraper_auth
def admin_delete_question(question_id):
    conn = get_db_connection()
    conn.execute('DELETE FROM questions WHERE id = ?', (question_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/admin/projects/<int:project_id>/publisher')
@_require_scraper_auth
def admin_get_project_publisher(project_id):
    conn = get_db_connection()
    row = conn.execute(
        'SELECT pu.id as publisher_id, pu.name as publisher, '
        'COUNT(DISTINCT p2.id) as project_count, '
        'COUNT(DISTINCT q.id) as question_count, '
        'COUNT(DISTINCT du.id) as url_count, '
        'COUNT(DISTINCT du.exam_name) as exam_count '
        'FROM projects p '
        'JOIN publishers pu ON pu.id = p.publisher_id '
        'LEFT JOIN projects p2 ON p2.publisher_id = pu.id '
        'LEFT JOIN questions q ON q.project_id = p2.id '
        'LEFT JOIN discovered_urls du ON du.publisher = pu.name '
        'WHERE p.id = ?',
        (project_id,)
    ).fetchone()
    if not row or not row['publisher']:
        conn.close()
        return jsonify({'error': 'No publisher linked to this project'}), 404
    conn.close()
    return jsonify(dict(row))

@app.route('/api/admin/publishers/<publisher_name>', methods=['DELETE'])
@_require_scraper_auth
def admin_delete_publisher(publisher_name):
    conn = get_db_connection()
    pub = conn.execute('SELECT id FROM publishers WHERE name = ?', (publisher_name,)).fetchone()
    if not pub:
        conn.close()
        return jsonify({'error': 'Publisher not found'}), 404

    project_ids = [r['id'] for r in conn.execute(
        'SELECT id FROM projects WHERE publisher_id = ?', (pub['id'],)
    ).fetchall()]
    if project_ids:
        ph = ','.join('?' * len(project_ids))
        conn.execute(f'DELETE FROM questions WHERE project_id IN ({ph})', project_ids)
        conn.execute(f'DELETE FROM projects WHERE id IN ({ph})', project_ids)

    conn.execute('DELETE FROM discovered_urls WHERE publisher = ?', (publisher_name,))
    conn.execute('DELETE FROM publishers WHERE id = ?', (pub['id'],))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

if __name__ == '__main__':
    app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true', host='0.0.0.0', port=5000)
