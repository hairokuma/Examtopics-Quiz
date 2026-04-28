#!/usr/bin/env python3
"""
Script to organize ExamTopics discussion URLs into separate files by exam name.
Extracts exam-name from URLs and creates a .txt file for each exam.
python sort_urls.py <input_file>
"""

import re
import sys
from collections import defaultdict
from pathlib import Path

def extract_exam_name(url):
    """
    Extract exam name from URL.
    Returns exam name (e.g., 'az-104', 'dp-600') or None if not found.
    """
    # Pattern: exam-{exam-name}-topic-
    # Example: exam-az-104-topic-16-question-2
    match = re.search(r'-exam-([a-z0-9-]+?)-topic-', url)
    if match:
        return match.group(1)
    
    # Try to extract exam name without topic
    exam_match = re.search(r'-exam-([a-z0-9-]+)', url)
    if exam_match:
        return exam_match.group(1)
    
    return None

def extract_exam_topic_question(url):
    """
    Extract exam name, topic and question numbers from URL for sorting.
    Returns tuple (exam_name, topic_num, question_num) for sorting.
    """
    match = re.search(r'-exam-([a-z0-9-]+?)-topic-(\d+)-question-(\d+)', url)
    if match:
        exam_name = match.group(1)
        topic_num = int(match.group(2))
        question_num = int(match.group(3))
        return (exam_name, topic_num, question_num)
    
    # For URLs without topic-question
    exam_name = extract_exam_name(url)
    if exam_name:
        return (exam_name, 999999, 999999)
    
    return ('zzz-unknown', 999999, 999999)

def organize_urls_by_exam(input_file):
    """
    Organize URLs from input file into separate exam files.
    
    Args:
        input_file: Path to input file with URLs
    """
    # Read all URLs
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]
    except IOError as e:
        print(f"Error reading file: {e}", file=sys.stderr)
        return
    
    print(f"Read {len(urls)} URLs from {input_file}")
    
    # Group URLs by exam name
    exam_urls = defaultdict(list)
    unknown_urls = []
    
    for url in urls:
        exam_name = extract_exam_name(url)
        if exam_name:
            exam_urls[exam_name].append(url)
        else:
            unknown_urls.append(url)
    
    # Sort URLs within each exam
    for exam_name in exam_urls:
        exam_urls[exam_name].sort(key=extract_exam_topic_question)
    
    # Get directory of input file and create exams folder
    input_path = Path(input_file)
    output_dir = input_path.parent / "exams"
    output_dir.mkdir(exist_ok=True)
    
    # Write each exam to its own file
    total_written = 0
    for exam_name, urls in sorted(exam_urls.items()):
        output_file = output_dir / f"{exam_name}.txt"
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for url in urls:
                    f.write(f"{url}\n")
            print(f"Wrote {len(urls)} URLs to {output_file}")
            total_written += len(urls)
        except IOError as e:
            print(f"Error writing file {output_file}: {e}", file=sys.stderr)
    
    # Write unknown URLs if any
    if unknown_urls:
        unknown_file = output_dir / "unknown-exam.txt"
        try:
            with open(unknown_file, 'w', encoding='utf-8') as f:
                for url in unknown_urls:
                    f.write(f"{url}\n")
            print(f"Wrote {len(unknown_urls)} unrecognized URLs to {unknown_file}")
            total_written += len(unknown_urls)
        except IOError as e:
            print(f"Error writing file {unknown_file}: {e}", file=sys.stderr)
    
    print(f"\nTotal: {total_written} URLs organized into {len(exam_urls)} exam files")

def main():
    """Main function."""
    if len(sys.argv) < 2:
        print("Usage: python sort_urls.py <input_file>")
        print("Example: python sort_urls.py databricks_discussions.txt")
        print("This will create separate .txt files for each exam (e.g., az-104.txt, dp-600.txt)")
        sys.exit(1)
    
    input_file = sys.argv[1]
    
    organize_urls_by_exam(input_file)

if __name__ == "__main__":
    main()
