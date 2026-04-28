from flask import Flask, render_template, request, jsonify
import sqlite3
import json
from datetime import datetime
from pathlib import Path

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
DATABASE = BASE_DIR.parent / 'app/data' / 'examtopics.db'

def get_db_connection():
    conn = sqlite3.connect(str(DATABASE))
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/')
def index():
    """Show project selection page"""
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
    return render_template('index.html', projects=projects_with_counts)

@app.route('/search')
@app.route('/search/<int:project_id>')
def search(project_id=None):
    """Show search page for a specific project or all projects"""
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
    """Search for questions"""
    query = request.args.get('q', '').strip()
    project_id = request.args.get('project_id', type=int)
    exclude_case_study = request.args.get('exclude_case_study', 'false').lower() == 'true'
    
    if len(query) < 3:
        return jsonify([])
    
    conn = get_db_connection()
    
    # Check if query is in quotes - if so, search for exact phrase
    if (query.startswith('"') and query.endswith('"')) or (query.startswith("'") and query.endswith("'")):
        # Remove quotes and search for exact phrase
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
        # Split query into words and create search conditions for each word
        words = query.split()
        
        # Build WHERE clause - each word must be found in either question_text or answer_object
        where_clauses = []
        params = []
        
        for word in words:
            if len(word) >= 2:  # Only search for words with at least 2 characters
                search_pattern = f'%{word}%'
                where_clauses.append('(q.question_text LIKE ? OR q.answer_object LIKE ?)')
                params.extend([search_pattern, search_pattern])
        
        # If no valid words, return empty
        if not where_clauses:
            conn.close()
            return jsonify([])
        
        # Combine all conditions with AND
        where_clause = ' AND '.join(where_clauses)
        
        # Build relevance score - sum of occurrences of all words
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
        
        # Build correct answers text
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
    """Show quiz interface for selected project"""
    conn = get_db_connection()
    project = conn.execute('SELECT * FROM projects WHERE id = ?', (project_id,)).fetchone()
    conn.close()
    
    if not project:
        return "Project not found", 404
    
    return render_template('quiz.html', project=project)

@app.route('/api/questions/<int:project_id>')
def get_questions(project_id):
    """Get all questions for a project"""
    conn = get_db_connection()
    questions = conn.execute('''
        SELECT *
        FROM questions 
        WHERE project_id = ? 
        ORDER BY topic_id, question_id
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
    """Submit user's answer and check if correct"""
    data = request.json
    question_id = data['question_id']
    user_answers = sorted(data['user_answers'])
    
    conn = get_db_connection()
    question = conn.execute(
        'SELECT correct_answer_keys FROM questions WHERE id = ?',
        (question_id,)
    ).fetchone()
    
    if not question:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404
    
    correct_answers = sorted(json.loads(question['correct_answer_keys']))
    is_correct = user_answers == correct_answers
    
    # Update question with user's answer
    conn.execute('''
        UPDATE questions 
        SET user_answer_keys = ?, 
            is_correct = ?, 
            answered_at = ?,
            updated_at = ?
        WHERE id = ?
    ''', (
        json.dumps(user_answers),
        1 if is_correct else 0,
        datetime.now().isoformat(),
        datetime.now().isoformat(),
        question_id
    ))
    conn.commit()
    conn.close()
    
    return jsonify({
        'correct': is_correct,
        'correct_answers': correct_answers,
        'user_answers': user_answers
    })

@app.route('/api/toggle_mark/<int:question_id>', methods=['POST'])
def toggle_mark(question_id):
    """Toggle the marked status of a question"""
    conn = get_db_connection()
    question = conn.execute(
        'SELECT is_marked FROM questions WHERE id = ?',
        (question_id,)
    ).fetchone()
    
    if not question:
        conn.close()
        return jsonify({'error': 'Question not found'}), 404
    
    new_marked_status = 0 if question['is_marked'] else 1
    conn.execute(
        'UPDATE questions SET is_marked = ?, updated_at = ? WHERE id = ?',
        (new_marked_status, datetime.now().isoformat(), question_id)
    )
    conn.commit()
    conn.close()
    
    return jsonify({'is_marked': new_marked_status})

@app.route('/api/stats/<int:project_id>')
def get_stats(project_id):
    """Get statistics for a project"""
    conn = get_db_connection()
    stats = conn.execute('''
        SELECT 
            COUNT(*) as total,
            SUM(CASE WHEN answered_at IS NOT NULL THEN 1 ELSE 0 END) as answered,
            SUM(CASE WHEN is_correct = 1 THEN 1 ELSE 0 END) as correct,
            SUM(CASE WHEN is_marked = 1 THEN 1 ELSE 0 END) as marked
        FROM questions 
        WHERE project_id = ?
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
    """Reset all progress for a project"""
    conn = get_db_connection()
    
    # Verify project exists
    project = conn.execute('SELECT id FROM projects WHERE id = ?', (project_id,)).fetchone()
    if not project:
        conn.close()
        return jsonify({'error': 'Project not found'}), 404
    
    # Reset all questions for this project
    conn.execute('''
        UPDATE questions 
        SET user_answer_keys = NULL,
            is_correct = NULL,
            answered_at = NULL,
            is_marked = 0,
            updated_at = ?
        WHERE project_id = ?
    ''', (datetime.now().isoformat(), project_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'message': 'Progress reset successfully'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
