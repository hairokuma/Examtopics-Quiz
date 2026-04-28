#!/usr/bin/env python3
"""
ExamTopics Data Scraper
Scrapes question data from ExamTopics URLs and stores in SQLite database
Usage: python scraper.py <urls_file> <project_id>
Example: python scraper.py dp-600.txt 4
"""

import sqlite3
import json
import re
import time
from bs4 import BeautifulSoup
import requests
from datetime import datetime
import sys

DATABASE = 'examtopics.db'

def get_db_connection():
    """Create database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def create_scraped_table():
    """Create questions_scraped table if it doesn't exist"""
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS questions_scraped (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER,
            topic_id INTEGER,
            question_id INTEGER,
            question_text TEXT,
            answer_object TEXT,
            correct_answer_keys TEXT,
            correct_answer_text TEXT,
            answered_at TEXT,
            user_answer_keys TEXT,
            is_correct INTEGER DEFAULT 0,
            is_marked INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            source_url TEXT
        )
    ''')
    conn.commit()
    conn.close()
    print("✓ Table questions_scraped ready")

def extract_question_id(soup):
    """Extract question number from question-discussion-header div"""
    header = soup.find('div', class_='question-discussion-header')
    if header:
        # Look for "Question #: 238" pattern
        question_match = re.search(r'Question\s*#:\s*(\d+)', header.get_text())
        if question_match:
            return int(question_match.group(1))
    return None

def extract_topic_id(soup):
    """Extract topic number from question-discussion-header div"""
    header = soup.find('div', class_='question-discussion-header')
    if header:
        # Look for "Topic #: 1" pattern
        topic_match = re.search(r'Topic\s*#:\s*(\d+)', header.get_text())
        if topic_match:
            return int(topic_match.group(1))
    return None

def scrape_question(url, session, project_id):
    """Scrape a single question from URL"""
    try:
        print(f"  Fetching: {url}")
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        question_body = soup.find('div', class_='question-body')
        
        if not question_body:
            print(f"  ⚠ No question body found")
            return None
        
        # Extract question text with images preserved
        question_text = extract_text_with_images(question_body.find('p', class_='card-text'))
        
        # Extract answers
        answers = {}
        correct_keys = []
        
        choices_container = question_body.find('div', class_='question-choices-container')
        if choices_container:
            # Normal multiple choice questions
            items = choices_container.find_all('li', class_='multi-choice-item')
            for item in items:
                letter_span = item.find('span', class_='multi-choice-letter')
                if letter_span:
                    letter = letter_span.get('data-choice-letter', '')
                    # Get answer text (remove the letter span)
                    letter_span.extract()
                    answer_text = extract_text_with_images(item).strip()
                    if letter and answer_text:
                        answers[letter] = answer_text
                    
                    # Check if it's marked as correct
                    if 'correct-hidden' in item.get('class', []):
                        correct_keys.append(letter)
        
        # Extract correct answer from "Suggested Answer" section
        answer_section = question_body.find('div', class_='question-answer')
        if answer_section:
            correct_span = answer_section.find('span', class_='correct-answer')
            if correct_span:
                # Check if correct answer contains an image
                answer_img = correct_span.find('img')
                if answer_img:
                    # Image-based answer
                    img_src = answer_img.get('src', '') or answer_img.get('data-src', '')
                    if img_src:
                        # Convert relative URLs to absolute URLs
                        if img_src.startswith('/'):
                            img_src = 'https://www.examtopics.com' + img_src
                        answers['A'] = img_src
                        correct_keys = ['A']
                else:
                    # Text-based correct answer
                    suggested = correct_span.get_text(strip=True)
                    # Handle multiple answers like "AB" or "A, B"
                    if not correct_keys:
                        correct_keys = [c for c in suggested.upper() if c.isalpha()]
        
        # Build correct answer text
        correct_text = ', '.join([f"{k}. {answers.get(k, '')}" for k in correct_keys])
        
        question_id = extract_question_id(soup)
        topic_id = extract_topic_id(soup)
        
        return {
            'project_id': project_id,
            'topic_id': topic_id,
            'question_id': question_id,
            'question_text': question_text,
            'answer_object': json.dumps(answers),
            'correct_answer_keys': json.dumps(correct_keys),
            'correct_answer_text': correct_text,
            'answered_at': None,
            'user_answer_keys': json.dumps([]),
            'is_correct': 0,
            'is_marked': 0,
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'source_url': url
        }
        
    except Exception as e:
        print(f"  ✗ Error scraping {url}: {e}")
        return None

def extract_text_with_images(element):
    """Extract text with image URLs inline"""
    if not element:
        return ""
    
    result = []
    
    for child in element.descendants:
        if child.name == 'img':
            src = child.get('src', '') or child.get('data-src', '')
            if src:
                # Convert relative URLs to absolute URLs
                if src.startswith('/'):
                    src = 'https://www.examtopics.com' + src
                result.append(f" {src} ")
        elif child.name == 'br':
            result.append('\n')
        elif isinstance(child, str):
            text = child.strip()
            if text:
                result.append(text)
    
    return ' '.join(result).strip()

def save_to_database(question_data):
    """Save question data to database"""
    conn = get_db_connection()
    
    # Check if question already exists with the same source_url
    existing = conn.execute(
        'SELECT id FROM questions_scraped WHERE project_id = ? AND question_id = ? AND source_url = ?',
        (question_data['project_id'], question_data['question_id'], question_data['source_url'])
    ).fetchone()
    
    if existing:
        # Update existing record with same source_url
        conn.execute('''
            UPDATE questions_scraped 
            SET topic_id = ?, question_text = ?, answer_object = ?, correct_answer_keys = ?,
                correct_answer_text = ?, updated_at = ?
            WHERE id = ?
        ''', (
            question_data['topic_id'],
            question_data['question_text'],
            question_data['answer_object'],
            question_data['correct_answer_keys'],
            question_data['correct_answer_text'],
            datetime.now().isoformat(),
            existing['id']
        ))
        print(f"  ✓ Updated T{question_data['topic_id']}-Q{question_data['question_id']} (same URL)")
    else:
        # Insert new
        conn.execute('''
            INSERT INTO questions_scraped 
            (project_id, topic_id, question_id, question_text, answer_object, correct_answer_keys,
             correct_answer_text, answered_at, user_answer_keys, is_correct, is_marked,
             created_at, updated_at, source_url)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            question_data['project_id'],
            question_data['topic_id'],
            question_data['question_id'],
            question_data['question_text'],
            question_data['answer_object'],
            question_data['correct_answer_keys'],
            question_data['correct_answer_text'],
            question_data['answered_at'],
            question_data['user_answer_keys'],
            question_data['is_correct'],
            question_data['is_marked'],
            question_data['created_at'],
            question_data['updated_at'],
            question_data['source_url']
        ))
        print(f"  ✓ Inserted T{question_data['topic_id']}-Q{question_data['question_id']}")
    
    conn.commit()
    conn.close()

def main():
    """Main scraper function"""
    if len(sys.argv) < 3:
        print("Usage: python scraper.py <urls_file> <project_id>")
        print("Example: python scraper.py dp-600.txt 4")
        print("Example: python scraper.py dp-700.txt 3")
        sys.exit(1)
    
    urls_file = sys.argv[1]
    project_id = int(sys.argv[2])
    
    print("=" * 60)
    print("ExamTopics Data Scraper")
    print("=" * 60)
    print(f"URLs File: {urls_file}")
    print(f"Project ID: {project_id}")
    print("=" * 60)
    
    # Create table
    create_scraped_table()
    
    # Read URLs
    try:
        with open(urls_file, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        print(f"✗ File not found: {urls_file}")
        return
    
    print(f"Found {len(urls)} URLs to scrape\n")
    
    # Create session for connection reuse
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    success_count = 0
    fail_count = 0
    
    for i, url in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Processing...")
        
        question_data = scrape_question(url, session, project_id)
        
        if question_data:
            save_to_database(question_data)
            success_count += 1
        else:
            fail_count += 1
        
        # Delay to avoid rate limiting
        time.sleep(1)
    
    print("\n" + "=" * 60)
    print(f"Scraping complete!")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print("=" * 60)

if __name__ == '__main__':
    main()
