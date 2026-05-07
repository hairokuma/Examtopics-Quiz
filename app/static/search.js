let searchTimeout;
let specificSearch = false;
let excludeCaseStudy = false;
const searchInput = document.getElementById('searchInput');
const searchResults = document.getElementById('searchResults');
let focusModeActive = false;

searchInput.addEventListener('input', (e) => {
    clearTimeout(searchTimeout);
    const query = e.target.value.trim();
    if (query.length < 3) {
        searchResults.innerHTML = '<div class="search-info">Type at least 3 characters to start searching</div>';
        return;
    }
    searchTimeout = setTimeout(() => performSearch(query), 300);
});

function focusMode() {
    // hide header and result-header
    focusModeActive = true;
    document.querySelector('header').style.display = 'none';
    document.querySelectorAll('.result-header').forEach(el => el.style.display = 'none');
}
function toggleSpecificSearch(event) {
    specificSearch = !specificSearch;
    event.target.textContent = specificSearch ? '✅' : '⬜';
    const query = searchInput.value.trim();
    if (query.length >= 3) performSearch(query);
}

function toggleCaseStudyExclusion(event) {
    excludeCaseStudy = !excludeCaseStudy;
    event.target.textContent = excludeCaseStudy ? '❗' : '❕';
    const query = searchInput.value.trim();
    if (query.length >= 3) performSearch(query);
}

function clearSearch() {
    searchInput.value = '';
    searchInput.dispatchEvent(new Event('input'));
    searchInput.focus();
}

async function performSearch(query) {
    try {
        searchResults.innerHTML = '<div class="search-info">Searching...</div>';
        let searchQuery = query;
        if (specificSearch && !query.startsWith('"')) {
            searchQuery = `"${query}"`;
        }
        const excludeParam = excludeCaseStudy ? '&exclude_case_study=true' : '';
        const response = await fetch(`/api/search?q=${encodeURIComponent(searchQuery)}${PROJECT_ID ? '&project_id=' + PROJECT_ID : ''}${excludeParam}`);
        const results = await response.json();
        if (results.length === 0) {
            searchResults.innerHTML = '<div class="no-results">No results found</div>';
            return;
        }
        displayResults(results, searchQuery);
    } catch (error) {
        console.error('Search error:', error);
        searchResults.innerHTML = '<div class="no-results">Error performing search</div>';
    }
}

function highlightText(text, query) {
    if (!text || !query) return text;
    const parts = text.split(/(<[^>]+>)/g);
    if (query.startsWith('"') && query.endsWith('"')) {
        const searchPhrase = query.slice(1, -1).trim();
        if (searchPhrase.length < 2) return text;
        const regex = new RegExp(`(${escapeRegex(searchPhrase)})`, 'gi');
        return parts.map(part => {
            if (part.startsWith('<') && part.endsWith('>')) return part;
            return part.replace(regex, '<mark>$1</mark>');
        }).join('');
    } else {
        const words = query.split(/\s+/).filter(word => word.length >= 2);
        let result = parts;
        words.forEach(word => {
            const regex = new RegExp(`(${escapeRegex(word)})`, 'gi');
            result = result.map(part => {
                if (part.startsWith('<') && part.endsWith('>')) return part;
                return part.replace(regex, '<mark>$1</mark>');
            });
        });
        return result.join('');
    }
}

function displayResults(results, query) {
    let html = '';
    results.forEach(result => {
        const highlightedQuestion = highlightText(processTextWithImages(result.question_text), query);
        const highlightedCorrectAnswers = result.correct_answers_text.map(answer =>
            highlightText(processTextWithImages(answer), query)
        );
        const highlightedAnswers = result.answers_text.map(answer =>
            highlightText(processTextWithImages(answer), query)
        );
        html += `
        <div class="search-result-item">
          <div class="result-header" style="display: ${focusModeActive ? 'none' : 'block'}">
              <div class="result-meta">
                  <span class="result-project">${result.project_name}</span>
                  Topic ${result.topic_id} - Question ${result.question_id}
              </div>
              <a href="/quiz/${result.project_id}/question/${result.id}" class="btn btn-primary">
                  Go to Question →
              </a>
          </div>
          <div class="result-correct-answers">
            ${highlightedCorrectAnswers.map(answer => `<div class="result-answer">${answer}</div>`).join('')}
          </div>
          <div class="result-question">
              ${highlightedQuestion}
              <hr>
              ${highlightedAnswers.map(answer => `<div class="result-answer">${answer}</div>`).join('')}
          </div>
        </div>`;
    });
    searchResults.innerHTML = html;
    document.getElementById('answerCount').textContent = results.length;
}
