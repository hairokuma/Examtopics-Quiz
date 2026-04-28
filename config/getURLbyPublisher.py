#!/usr/bin/env python3
"""
Script to scrape discussion URLs from ExamTopics by publisher.
Extracts all discussion links from paginated pages.
"""

import requests
from bs4 import BeautifulSoup
import re
import time
import sys
from urllib.parse import urljoin

def get_page_content(url, session):
    """Fetch page content with error handling."""
    try:
        response = session.get(url, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url}: {e}", file=sys.stderr)
        return None

def extract_total_pages(soup):
    """Extract the total number of pages from pagination."""
    pagination = soup.find('span', class_='discussion-list-page-indicator')
    if pagination:
        # Look for "of <strong>1447</strong>" pattern
        match = re.search(r'of\s+<strong>(\d+)</strong>', str(pagination))
        if match:
            return int(match.group(1))
    return 1

def extract_discussion_urls(soup, base_url):
    """Extract discussion URLs from the discussion-list container."""
    urls = []
    discussion_list = soup.find('div', class_='discussion-list')
    
    if discussion_list:
        # Find all links within the discussion list
        links = discussion_list.find_all('a', href=True)
        for link in links:
            href = link['href']
            # Filter for discussion URLs (contains /discussions/ and /view/)
            if '/discussions/' in href and '/view/' in href:
                full_url = urljoin(base_url, href)
                if full_url not in urls:
                    urls.append(full_url)
    
    return urls

def scrape_publisher_discussions(publisher, output_file=None, delay=1.0):
    """
    Scrape all discussion URLs for a given publisher.
    
    Args:
        publisher: Publisher name (e.g., 'microsoft')
        output_file: Optional file path to write URLs
        delay: Delay between requests in seconds
    """
    base_url = f"https://www.examtopics.com/discussions/{publisher}/"
    all_urls = []
    
    # Create session for connection pooling
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    print(f"Fetching first page to determine total pages...")
    
    # Get first page to determine total pages
    first_page_url = f"{base_url}1/"
    html_content = get_page_content(first_page_url, session)
    
    if not html_content:
        print("Failed to fetch first page. Exiting.")
        return []
    
    soup = BeautifulSoup(html_content, 'html.parser')
    total_pages = extract_total_pages(soup)
    
    print(f"Found {total_pages} pages to scrape")
    
    # Open output file for writing (if specified)
    output_handle = None
    if output_file:
        try:
            output_handle = open(output_file, 'w', encoding='utf-8')
        except IOError as e:
            print(f"Error opening file: {e}", file=sys.stderr)
            return []
    
    # Extract URLs from first page
    urls = extract_discussion_urls(soup, base_url)
    all_urls.extend(urls)
    
    # Write URLs immediately after extraction
    if output_handle:
        for url in urls:
            output_handle.write(f"{url}\n")
        output_handle.flush()
    
    print(f"Page 1/{total_pages}: Found {len(urls)} discussion URLs")
    
    # Process remaining pages
    for page_num in range(2, total_pages + 1):
        time.sleep(delay)  # Be polite to the server
        
        page_url = f"{base_url}{page_num}/"
        html_content = get_page_content(page_url, session)
        
        if not html_content:
            print(f"Skipping page {page_num} due to error")
            continue
        
        soup = BeautifulSoup(html_content, 'html.parser')
        urls = extract_discussion_urls(soup, base_url)
        all_urls.extend(urls)
        
        # Write URLs immediately after extraction
        if output_handle:
            for url in urls:
                output_handle.write(f"{url}\n")
            output_handle.flush()
        
        print(f"Page {page_num}/{total_pages}: Found {len(urls)} discussion URLs (Total: {len(all_urls)})")
    
    # Close file if it was opened
    if output_handle:
        output_handle.close()
        print(f"\nWrote {len(all_urls)} URLs to {output_file}")
    
    return all_urls

def main():
    """Main function to run the scraper."""
    if len(sys.argv) < 2:
        print("Usage: python getURLbyPublisher.py <publisher> [output_file] [delay]")
        print("Example: python getURLbyPublisher.py microsoft microsoft_discussions.txt 1.0")
        sys.exit(1)
    
    publisher = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else f"{publisher}_discussions.txt"
    delay = float(sys.argv[3]) if len(sys.argv) > 3 else 1.0
    
    print(f"Starting scraper for publisher: {publisher}")
    print(f"Output file: {output_file}")
    print(f"Delay between requests: {delay}s\n")
    
    urls = scrape_publisher_discussions(publisher, output_file, delay)
    
    print(f"\nCompleted! Total URLs collected: {len(urls)}")

if __name__ == "__main__":
    main()
