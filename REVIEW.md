# Code Review — `app/`

Reviewed: 2026-04-29  
Scope: `app/app.py`, `app/static/*.js`, `app/templates/`, `app/Dockerfile`, `app/requirements.txt`

---

## Critical — Security

### CR-01 · XSS via unescaped URLs in quiz.js

**File:** [app/static/quiz.js:162-163](app/static/quiz.js#L162-L163)

`question.source_url` is injected into an HTML template string without escaping:

```js
<a href="${question.source_url}" target="_blank">🔗</a>
```

A scraped URL containing `"` or javascript: scheme would execute arbitrary JS. Run all user-originated strings through `escapeHtml` (already defined in `utils.js`) before injecting into innerHTML.

---

### CR-02 · XSS in scraper.js onclick interpolation

**File:** [app/static/scraper.js:29](app/static/scraper.js#L29), [app/static/scraper.js:103-109](app/static/scraper.js#L103-L109)

Publisher names and exam names are interpolated raw into onclick attribute strings:

```js
onclick="selectPublisher('${p.name}')"
onclick="openCreateModal('${publisher}', '${e.exam_name}')"
```

A publisher or exam name containing a single quote breaks the onclick and could inject arbitrary JS. Store data in `data-*` attributes and bind listeners instead of inline handlers.

---

### CR-03 · SQL injection pattern in `_update_job`

**File:** [app/app.py:157](app/app.py#L157)

Column names from `kwargs` are directly interpolated into the SQL statement:

```python
set_parts = [f'{k} = ?' for k in kwargs]
```

The values are parameterised but the column names are not. All current call sites pass string literals, so this is not exploitable today — but the pattern is dangerous because a future caller passing user-controlled keys would open SQL injection. Use an allowlist of valid column names.

---

### CR-04 · Internal error messages leaked to clients

**File:** [app/app.py:853-854](app/app.py#L853-L854)

```python
return jsonify({'error': str(e)}), 500
```

Raw Python exception messages (stack traces, file paths, library internals) are returned to the browser. Log the exception server-side and return a generic message to the client.

---

### CR-05 · `debug=True` hardcoded

**File:** [app/app.py:965](app/app.py#L965)

```python
app.run(debug=True, host='0.0.0.0', port=5000)
```

Debug mode exposes an interactive debugger over the network. Gate on an environment variable:

```python
app.run(debug=os.getenv('FLASK_DEBUG', 'false').lower() == 'true', host='0.0.0.0', port=5000)
```

---

### CR-06 · Missing input validation on `submit_answer`

**File:** [app/app.py:650-653](app/app.py#L650-L653)

```python
data = request.json
question_id = data['question_id']
user_answers = sorted(data['user_answers'])
```

If `request.json` is `None` or either key is absent this raises an unhandled `TypeError`/`KeyError` and returns a 500. Validate the presence and type of `question_id` and `user_answers` before use.

---

## High — Architecture & Performance

### CR-07 · One DB connection per operation — no pooling

**File:** [app/app.py:18-21](app/app.py#L18-L21), [app/app.py:420-432](app/app.py#L420-L432)

`get_db_connection()` opens a new connection on every call and closes it immediately. During question scraping, each iteration opens and closes two separate connections (`_save_scraped_question` + the `scraped = 1` update). For a 500-question scrape this is ~1000 open/close cycles.

**Change request:** Pass a connection into helper functions rather than opening a new one each time. For the scrape loop, keep one connection open for the duration of the job and commit in batches.

---

### CR-08 · Log append is O(n) in job log size

**File:** [app/app.py:165-178](app/app.py#L165-L178)

`_log_job` reads the entire `log` JSON column, deserialises it, appends one entry, and writes the full array back on every call. For a 500-question job logging every 25 steps this is still 20 full read-modify-write cycles on a growing blob.

**Change request:** Move job logs to a separate `job_logs` table with one row per entry so appends are `INSERT` not `UPDATE`.

---

### CR-09 · URL discovery deletes before completing

**File:** [app/app.py:385](app/app.py#L385)

```python
conn.execute('DELETE FROM discovered_urls WHERE publisher = ?', (publisher,))
```

All existing URLs for the publisher are deleted before the new crawl results are written. If the job fails mid-write, all previously discovered URLs are gone permanently.

**Change request:** Write new URLs into a staging set or use `INSERT OR REPLACE`. Only drop stale rows after the new set is successfully committed.

---

### CR-10 · All questions loaded in a single API call

**File:** [app/app.py:633-647](app/app.py#L633-L647), [app/static/quiz.js:68-70](app/static/quiz.js#L68-L70)

`/api/questions/<project_id>` returns every question for the project as one JSON payload. For exams with hundreds of questions this sends all question text and answer data at once, before the user reads any of it.

**Change request:** At minimum paginate or stream questions. As a simple improvement, return only `id`, `topic_id`, `question_id`, `is_correct`, `is_marked` for the nav list and fetch the full question body on demand.

---

### CR-11 · Fragile database path construction

**File:** [app/app.py:16](app/app.py#L16)

```python
DATABASE = BASE_DIR.parent / 'app/data' / 'examtopics.db'
```

`BASE_DIR` is already `app/`, so this goes up one level then back into `app/data`. It works, but only because of the directory structure. Use:

```python
DATABASE = BASE_DIR / 'data' / 'examtopics.db'
```

---

## Medium — Code Quality

### CR-12 · Duplicated SQL branches in `api_search`

**File:** [app/app.py:497-621](app/app.py#L497-L621)

The exact-phrase path and the word-split path each have two nearly identical SQL queries (with and without `project_id`). The function is ~120 lines. Extract a helper that builds the WHERE clause and params, then assemble the final query once.

---

### CR-13 · Implicit global `event` in search.js

**File:** [app/static/search.js:18-19](app/static/search.js#L18-L19), [app/static/search.js:24-25](app/static/search.js#L24-L25)

```js
function toggleSpecificSearch() {
    specificSearch = !specificSearch;
    event.target.textContent = ...   // relies on window.event — deprecated
```

`event` as an implicit global is deprecated and does not work in Firefox strict mode. Pass the event as a parameter:

```js
function toggleSpecificSearch(event) { ... }
```

and update the `onclick` attribute accordingly.

---

### CR-14 · Nav item text truncated with raw substring

**File:** [app/static/quiz.js:109](app/static/quiz.js#L109)

```js
navItem.textContent = `T${question.topic_id}-Q${question.question_id} ${question.question_text.substring(0, 30)}...`;
```

`question_text` may contain embedded image URLs (which the app stores as plain text), so the 30-character truncation can show a partial URL. Also, the `...` is appended unconditionally even when the text is shorter than 30 chars. Fix:

```js
const preview = question.question_text.length > 30
    ? question.question_text.substring(0, 30) + '…'
    : question.question_text;
```

---

### CR-15 · Inline style mutations for disabled state in quiz.js

**File:** [app/static/quiz.js:281-283](app/static/quiz.js#L281-L283)

```js
document.querySelector('.btn-success').disabled = true;
document.querySelector('.btn-success').style.opacity = '0.5';
document.querySelector('.btn-success').style.cursor = 'not-allowed';
```

Styling is duplicated from CSS and managed imperatively. Add a CSS class (e.g. `.btn-disabled`) and toggle it with `classList.add`.

---

### CR-16 · `renderQuestionNav` called redundantly on every `showQuestion`

**File:** [app/static/quiz.js:198](app/static/quiz.js#L198)

`showQuestion` calls `renderQuestionNav()` at the end, which rebuilds the entire nav list DOM from scratch. It is also called after `submitAnswer` and `toggleMark`. Each call iterates all questions and replaces every DOM node. For large question sets this causes noticeable jank. Only update the affected nav items (previous active, new active, changed status).

---

### CR-17 · Mixed quote-style inconsistency in search API

**File:** [app/app.py:508](app/app.py#L508)

```python
if (query.startswith('"') and query.endswith('"')) or (query.startswith("'") and query.endswith("'")):
```

Allowing single-quoted phrases (`'foo'`) is undocumented and inconsistent with the UI's tooltip, which only mentions double quotes. Remove single-quote support or document it explicitly.

---

## Low — Housekeeping & Deployment

### CR-18 · Dockerfile runs as root

**File:** [app/Dockerfile](app/Dockerfile)

No `USER` instruction is present, so the container runs as root. Add:

```dockerfile
RUN useradd -r appuser
USER appuser
```

---

### CR-19 · No HEALTHCHECK in Dockerfile

**File:** [app/Dockerfile](app/Dockerfile)

Container orchestrators cannot detect when the app is unhealthy. Add:

```dockerfile
HEALTHCHECK --interval=30s --timeout=5s CMD curl -f http://localhost:5000/ || exit 1
```

---

### CR-20 · Requirements not pinned to patch versions

**File:** [app/requirements.txt](app/requirements.txt)

`Flask==3.0.0` and `requests==2.31.0` pin to minor versions but will pick up patch updates on rebuild, which can introduce breaking changes. Pin to exact patch versions and use a lock file approach (e.g. `pip-compile`).

---

### CR-21 · `questions` table mixes content and user-state

**File:** [app/app.py:46-61](app/app.py#L46-L61)

User progress columns (`user_answer_keys`, `is_correct`, `answered_at`, `is_marked`) live in the same row as question content. This makes it impossible to add multi-user support without a schema rewrite. Consider splitting into `questions` (content only) and `question_progress` (user state) even for a single-user case — it makes resets, re-imports, and future user isolation simpler.

---

---

## UI/UX — Usability Improvements

### UX-01 · Auto-start scrape after project creation

**File:** [app/static/scraper.js:275-298](app/static/scraper.js#L275-L298)

After `submitCreateProject()` closes the modal and reloads the exam list, the user must manually click "Scrape Questions" for the new project. Since project creation exists only to enable scraping, immediately start a scrape job upon successful creation:

```js
const project = await resp.json();
if (project.error) { alert(project.error); return; }
closeModal();
await loadExams(pendingPublisher);
startScrape(pendingPublisher, pendingExamName, project.id);
```

---

### UX-02 · Progressive import — allow importing while scraping

**File:** [app/static/scraper.js:153-161](app/static/scraper.js#L153-L161)

Currently the "Import to Quiz" button only appears after scraping finishes. For large exams (500+ questions) this means a long wait before anything is accessible. Enable the import button as soon as `scraped_question_count > 0`, even while the scrape job is running. The `import_questions` endpoint already handles duplicates via `source_url` deduplication, so repeated imports are safe.

---

### UX-03 · Project sort order — scraped projects first, then alphabetical

**File:** [app/app.py:463](app/app.py#L463)

```python
projects = conn.execute('SELECT * FROM projects ORDER BY name').fetchall()
```

Projects that have been imported and are ready to quiz should sort before empty/placeholder projects. Change the sort to put projects with questions first:

```python
projects = conn.execute(
    'SELECT * FROM projects ORDER BY (question_count > 0) DESC, name'
).fetchall()
```

Since `question_count` is computed per-project in the loop below, move the ordering into the Python sort after building `projects_with_counts`, or add a subquery.

---

### UX-04 · Add link to ExamTopics discussions index for publisher discovery

**File:** [app/templates/scraper.html:18-35](app/templates/scraper.html#L18-L35)

The publisher panel gives no starting point for finding valid publisher slugs. Add a direct link to the ExamTopics discussions index next to the "+" button:

```html
<a href="https://www.examtopics.com/discussions/" target="_blank"
   class="btn-sm" title="Browse ExamTopics publishers">↗ Browse</a>
```

This lets users look up the correct slug without leaving the page or guessing.

---



---

### UX-06 · Stats bar shows raw counts but no percentage

**File:** [app/templates/quiz.html:15-25](app/templates/quiz.html#L15-L25)

The header stats show `Progress: 12/200` and `Correct: 8` but no quick percentage. Users have to divide mentally to gauge how far they are. Show a percentage alongside the count:

```
Progress: 12/200 (6%) · Correct: 8 (67%) · Marked: 3
```

The percentage can be computed in `updateStats()` once the totals are available.

---

### UX-07 · "Start Quiz" button label ignores existing progress

**File:** [app/templates/index.html:20](app/templates/index.html#L20)

The button always reads "Start Quiz" even when `project.progress > 0`. The confirmation modal handles the case, but the button itself gives no hint that progress exists. Change the label server-side:

```html
<button ...>
    {{ 'Continue Quiz' if project.progress > 0 else 'Start Quiz' }}
</button>
```

This sets the right expectation before the modal appears.

---

### UX-08 · Confusing dual question count on project cards

**File:** [app/templates/index.html:19](app/templates/index.html#L19)

```
{{ project.questions }} ({{project.question_count}}) questions
```

Two numbers are shown side by side with no label explaining the difference (`questions` = count from ExamTopics metadata, `question_count` = actually imported rows). Users cannot tell which is authoritative. Show one number with a label, e.g.:

```
{{project.question_count}} questions imported · {{project.questions}} on ExamTopics
```

---

### UX-09 · Progress bar persists after job completion

**File:** [app/static/scraper.js:178-183](app/static/scraper.js#L178-L183)

When a scrape job finishes, the progress bar at the bottom stays visible permanently. It only disappears if a new job is started. Add a dismiss button or auto-hide after a short delay on completion:

```js
if (data.status === 'completed' || data.status === 'failed') {
    // ...existing code...
    setTimeout(() => {
        document.getElementById('progressBar').style.display = 'none';
    }, 5000);
}
```

---

### UX-10 · No sidebar filter for marked or incorrect questions

**File:** [app/templates/quiz.html:29-33](app/templates/quiz.html#L29-L33), [app/static/quiz.js:102-128](app/static/quiz.js#L102-L128)

The sidebar lists all questions in order with no way to jump to only the ones marked for review or answered incorrectly. These are the two main study use-cases (reviewing weak spots). Add simple filter buttons above the nav list:

```
[All] [Incorrect] [Marked]
```

Each filter narrows the visible nav items and resets navigation within that subset.

---

### UX-11 · Inconsistent navigation to homepage

**File:** [app/templates/quiz.html:29-33](app/templates/quiz.html#L29-L33), [app/templates/scraper.html:10-14](app/templates/scraper.html#L10-L14)

On quiz `<a href="/">← Back to Projects</a>` in `<nav class="question-list">`
On scraper `<a href="/" class="back-link">← Back</a>` in `<header>`

Make consistent (preferably the header link for better visibility) and ensure it is present on all pages for easy navigation.

## Summary

| Severity | Count |
|----------|-------|
| Critical — Security | 6 |
| High — Architecture / Performance | 5 |
| Medium — Code Quality | 6 |
| Low — Housekeeping | 4 |
| UI/UX — Usability | 10 |

Priority order for fixes: CR-01 → CR-02 → CR-05 → CR-03 → CR-04 → CR-06 → CR-09 → CR-07 → CR-10.
