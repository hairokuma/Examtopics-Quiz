let currentPublisher = null;
let cachedPublishers = [];
let pendingPublisher = null;
let pendingExamName = null;

// ─── Publishers ───────────────────────────────────────────────────────

async function loadPublishers() {
    document.getElementById('publisherItems').innerHTML =
        '<div class="placeholder">Loading...</div>';
    try {
        const resp = await fetch('/api/scraper/publishers');
        cachedPublishers = await resp.json();
        renderPublishers();
    } catch (e) {
        document.getElementById('publisherItems').innerHTML =
            '<div class="placeholder error">Failed to load</div>';
    }
}

function renderPublishers() {
    const container = document.getElementById('publisherItems');
    if (!cachedPublishers.length) {
        container.innerHTML = '<div class="placeholder">No publishers found</div>';
        return;
    }
    container.innerHTML = cachedPublishers.map(p => `
        <div class="item ${p.name === currentPublisher ? 'active' : ''}"
             data-publisher="${escapeHtml(p.name)}">
            <div class="pub-name">${escapeHtml(p.name)}</div>
            <div class="pub-meta">
                ${p.url_count ? `${p.exam_count} exams · ${p.url_count} URLs` : 'Not discovered'}
            </div>
        </div>
    `).join('');
    container.querySelectorAll('.item').forEach(el => {
        el.addEventListener('click', () => selectPublisher(el.dataset.publisher));
    });
}

function selectPublisher(name) {
    currentPublisher = name;
    renderPublishers();
    loadExams(name);
}

// ─── Exams ────────────────────────────────────────────────────────────

async function loadExams(publisher) {
    const p = cachedPublishers.find(x => x.name === publisher);
    const hasUrls = p && p.url_count > 0;

    document.getElementById('examContent').innerHTML = `
        <div style="padding:16px;border-bottom:1px solid #333;display:flex;align-items:center;gap:12px;">
            <span style="font-size:16px;font-weight:500;text-transform:capitalize;">${escapeHtml(publisher)}</span>
            <button class="btn-sm primary" id="discoverBtn">
                ${hasUrls ? '↻ Re-discover URLs' : '+ Discover URLs'}
            </button>
            ${hasUrls ? `<span style="font-size:12px;color:#666;">${p.url_count} URLs · ${p.exam_count} exams</span>` : ''}
        </div>
        ${hasUrls ? '<div id="examGrid" style="padding-bottom:60px;"><div class="placeholder">Loading exams...</div></div>'
                  : '<div class="placeholder" style="margin-top:40px;">No URLs discovered yet. Click "Discover URLs" to start.</div>'}
    `;

    document.getElementById('discoverBtn')?.addEventListener('click', () => startDiscovery(publisher));

    if (!hasUrls) return;

    try {
        const resp = await fetch(`/api/scraper/exams/${publisher}`);
        const exams = await resp.json();
        renderExams(publisher, exams);
    } catch (e) {
        document.getElementById('examGrid').innerHTML =
            '<div class="placeholder error">Failed to load exams</div>';
    }
}

function renderExams(publisher, exams) {
    const grid = document.getElementById('examGrid');
    if (!exams.length) {
        grid.innerHTML = '<div class="placeholder">No exams found</div>';
        return;
    }
    grid.innerHTML = `<div class="grid">${exams.map(e => examCard(publisher, e)).join('')}</div>`;
    grid.querySelectorAll('[data-action]').forEach(el => {
        el.addEventListener('click', () => {
            const {action, publisher: pub, exam, projectId} = el.dataset;
            if (action === 'create') openCreateModal(pub, exam);
            else if (action === 'scrape') startScrape(pub, exam, parseInt(projectId));
            else if (action === 'import') importQuestions(parseInt(projectId), pub, exam);
        });
    });
}

function examCard(publisher, e) {
    const hasProject = !!e.project_id;
    const allScraped = e.scraped_url_count >= e.url_count;
    const hasImported = e.imported_question_count > 0;
    const pubAttr = escapeHtml(publisher);
    const examAttr = escapeHtml(e.exam_name);

    return `
        <div class="card" id="exam-${examAttr}">
            <h3>${escapeHtml(e.exam_name)}</h3>
            <div class="card-meta">
                <span>${e.url_count} URLs</span>
                ${e.scraped_url_count > 0 ? `<span class="${allScraped ? 'ok' : ''}">${e.scraped_url_count} scraped</span>` : ''}
                ${hasProject ? `<span style="color:#aaa;">${escapeHtml(e.project_name)}</span>` : ''}
            </div>
            ${hasProject ? `
                <div class="card-meta">
                    <span>${e.scraped_question_count} staged</span>
                    ${e.imported_question_count > 0 ? `<span class="ok">${e.imported_question_count} in quiz</span>` : ''}
                </div>` : ''}
            <div class="card-actions">
                ${!hasProject
                    ? `<button class="btn-sm primary" data-action="create" data-publisher="${pubAttr}" data-exam="${examAttr}">Create Project</button>`
                    : `<button class="btn-sm primary" data-action="scrape" data-publisher="${pubAttr}" data-exam="${examAttr}" data-project-id="${e.project_id}">
                           ${e.scraped_question_count > 0 ? '↻ Re-scrape' : 'Scrape Questions'}
                       </button>`
                }
                ${hasProject && e.scraped_question_count > 0
                    ? `<button class="btn-sm" data-action="import" data-project-id="${e.project_id}" data-publisher="${pubAttr}" data-exam="${examAttr}">
                           ${hasImported ? '↻ Re-import' : 'Import to Quiz'}
                       </button>`
                    : ''}
            </div>
        </div>
    `;
}


// ─── URL Discovery ────────────────────────────────────────────────────

async function startDiscovery(publisher) {
    try {
        const resp = await fetch('/api/scraper/start_discovery', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({publisher, delay: 1.5})
        });
        const {job_id} = await resp.json();
        startProgressStream(job_id, `Discovering ${publisher} URLs`, async () => {
            await loadPublishers();
            selectPublisher(publisher);
        });
    } catch (e) {
        alert('Failed to start discovery: ' + e.message);
    }
}

// ─── Question Scraping ────────────────────────────────────────────────

async function startScrape(publisher, examName, projectId) {
    try {
        const resp = await fetch('/api/scraper/start_scrape', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({publisher, exam_name: examName, project_id: projectId, delay: 1.0})
        });
        const {job_id} = await resp.json();
        startProgressStream(job_id, `Scraping ${examName}`, () => loadExams(publisher));
    } catch (e) {
        alert('Failed to start scrape: ' + e.message);
    }
}

async function importQuestions(projectId, publisher, examName) {
    try {
        const resp = await fetch(`/api/scraper/import/${projectId}`, {method: 'POST'});
        const result = await resp.json();
        alert(`Import complete: ${result.imported} imported, ${result.skipped} already existed`);
        loadExams(publisher);
    } catch (e) {
        alert('Import failed: ' + e.message);
    }
}

// ─── Progress Stream ──────────────────────────────────────────────────

let activeEventSource = null;

function startProgressStream(job_id, label, onComplete) {
    if (activeEventSource) activeEventSource.close();

    showProgress(label);
    document.getElementById('logBox').innerHTML = '';

    activeEventSource = new EventSource(`/api/scraper/stream/${job_id}`);
    activeEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateProgress(data);
        if (data.status === 'completed' || data.status === 'failed') {
            activeEventSource.close();
            activeEventSource = null;
            const statusText = data.status === 'completed' ? 'Done' : 'Failed';
            document.getElementById('progressLabel').textContent = `${label} — ${statusText}`;
            setTimeout(() => {
                document.getElementById('progressBar').style.display = 'none';
            }, 5000);
            if (onComplete) onComplete();
        }
    };
    activeEventSource.onerror = () => {
        if (activeEventSource) activeEventSource.close();
        activeEventSource = null;
    };
}

function showProgress(label) {
    document.getElementById('progressBar').style.display = 'flex';
    document.getElementById('progressLabel').textContent = label;
    document.getElementById('progressFill').style.width = '0%';
    document.getElementById('progressPct').textContent = '0 / 0';
}

function updateProgress(data) {
    const pct = data.total > 0 ? Math.round(data.processed / data.total * 100) : 0;
    document.getElementById('progressFill').style.width = pct + '%';
    document.getElementById('progressPct').textContent =
        `${data.processed} / ${data.total}` +
        (data.success_count > 0 || data.fail_count > 0
            ? ` · ${data.success_count} ok${data.fail_count > 0 ? ` · ${data.fail_count} ✗` : ''}` : '');

    if (data.new_log && data.new_log.length) {
        const logBox = document.getElementById('logBox');
        data.new_log.forEach(entry => {
            const line = document.createElement('div');
            line.className = 'log-line';
            line.innerHTML = `<span class="log-ts">${entry.time}</span>${escapeHtml(entry.msg)}`;
            logBox.appendChild(line);
        });
        logBox.scrollTop = logBox.scrollHeight;
    }
}

function toggleLog() {
    const box = document.getElementById('logBox');
    const btn = document.getElementById('logToggle');
    if (box.style.display === 'none' || !box.style.display) {
        box.style.display = 'block';
        btn.textContent = 'hide log';
    } else {
        box.style.display = 'none';
        btn.textContent = 'show log';
    }
}

// ─── Create Project Modal ─────────────────────────────────────────────

function openCreateModal(publisher, examName) {
    const p = cachedPublishers.find(x => x.name === publisher);
    pendingPublisher = publisher;
    pendingExamName = examName;
    document.getElementById('modalExamName').textContent = examName;
    document.getElementById('projectLink').value = `https://www.examtopics.com/${publisher}/${examName}/view/`;
    document.getElementById('projectName').value = `${publisher} ${examName}`;
    document.getElementById('projectDescription').value = '';
    document.getElementById('projectQuestions').value = p.url_count || '';
    document.getElementById('projectLastUpdated').value = '';
    document.getElementById('createModal').classList.add('open');
}

function closeModal() {
    document.getElementById('createModal').classList.remove('open');
}

async function fetchProjectInfo() {
    const link = document.getElementById('projectLink').value.trim();
    if (!link) return;
    const btn = document.getElementById('fetchInfoBtn');
    btn.disabled = true;
    btn.textContent = '...';
    try {
        const resp = await fetch('/api/scraper/fetch_project_info', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({link})
        });
        const info = await resp.json();
        if (info.question_count) document.getElementById('projectQuestions').value = info.question_count;
        if (info.last_updated) document.getElementById('projectLastUpdated').value = info.last_updated;
        if (info.description && !document.getElementById('projectDescription').value) {
            document.getElementById('projectDescription').value = info.description;
        }
    } catch (e) {
        alert('Could not fetch project info: ' + e.message);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Fetch';
    }
}

async function submitCreateProject() {
    const name = document.getElementById('projectName').value.trim();
    if (!name) { alert('Name is required'); return; }
    try {
        const resp = await fetch('/api/scraper/create_project', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                name,
                link: document.getElementById('projectLink').value.trim(),
                description: document.getElementById('projectDescription').value.trim(),
                questions: parseInt(document.getElementById('projectQuestions').value) || null,
                last_updated_on: document.getElementById('projectLastUpdated').value.trim(),
                publisher: pendingPublisher,
                exam_name: pendingExamName
            })
        });
        const project = await resp.json();
        if (project.error) { alert(project.error); return; }
        closeModal();
        await loadExams(pendingPublisher);
        startScrape(pendingPublisher, pendingExamName, project.id);
    } catch (e) {
        alert('Failed to create project: ' + e.message);
    }
}

// ─── Add Custom Publisher ─────────────────────────────────────────────

function toggleAddPublisher() {
    const form = document.getElementById('addPublisherForm');
    const visible = form.style.display !== 'none';
    form.style.display = visible ? 'none' : 'block';
    if (!visible) document.getElementById('publisherUrlInput').focus();
}

async function addPublisher() {
    const raw = document.getElementById('publisherUrlInput').value.trim();
    if (!raw) return;
    const m = raw.match(/\/discussions\/([a-z0-9-]+)/i);
    const name = m ? m[1].toLowerCase() : raw.toLowerCase().replace(/[^a-z0-9-]/g, '');
    if (!name) { alert('Could not parse publisher name from input'); return; }

    document.getElementById('publisherUrlInput').value = '';
    toggleAddPublisher();

    await fetch('/api/scraper/publishers', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name})
    });

    await loadPublishers();
    selectPublisher(name);
}

// ─── Init ─────────────────────────────────────────────────────────────

window.onclick = (e) => {
    if (e.target === document.getElementById('createModal')) closeModal();
};

loadPublishers();
