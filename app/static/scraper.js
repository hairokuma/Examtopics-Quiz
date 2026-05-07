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
            <p>${escapeHtml(p.name)}</p>
            <span>
                ${p.url_count ? `${p.exam_count} exams · ${p.url_count} URLs` : 'Not discovered'}
            </span>
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
    _refreshDiscoverPublisherBtn();
}

// ─── Exams ────────────────────────────────────────────────────────────

async function loadExams(publisher) {
    try {
        const resp = await fetch(`/api/scraper/exams/${publisher}`);
        const exams = await resp.json();
        renderExams(publisher, exams);
    } catch (e) {
        document.getElementById('examPanel').innerHTML =
            '<div class="placeholder error">Failed to load exams</div>';
    }
}

function renderExams(publisher, exams) {
    const grid = document.getElementById('examPanel');
    if (!exams.length) {
        const p = cachedPublishers.find(x => x.name === publisher);
        const hasUrls = p && p.url_count > 0;

        const isDiscovering = activeJobInfo && activeJobInfo.job_type === 'url_discovery';
        const discoverLabel = isDiscovering ? 'Discovering...' : (hasUrls ? '↻ Re-discover URLs' : '+ Discover URLs');
        grid.innerHTML = `<div class="placeholder">No exams found
        <button class="btn primary" id="discoverBtn" ${isDiscovering ? 'disabled' : ''}>
        ${discoverLabel}
        </button>
        </div>
        `;
        document.getElementById('discoverBtn')?.addEventListener('click', () => startDiscovery(publisher));

        return;
    }
    grid.innerHTML = `<div class="grid">${exams.map(e => examCard(publisher, e)).join('')}</div>`;
    grid.querySelectorAll('[data-action]').forEach(el => {
        el.addEventListener('click', () => {
            const { action, publisher: pub, exam, projectId } = el.dataset;
            if (action === 'create') openCreateModal(pub, exam);
            else if (action === 'scrape') startScrape(pub, exam, parseInt(projectId));
        });
    });
}

function examCard(publisher, e) {
    const hasProject = !!e.project_id;
    const allScraped = e.scraped_url_count >= e.url_count;
    const pubAttr = escapeHtml(publisher);
    const examAttr = escapeHtml(e.exam_name);

    return `
        <div class="card" id="exam-${examAttr}">
            <h2>${escapeHtml(e.exam_name)}</h2>
            <p>${e.url_count} URLs${hasProject ? ` · ${escapeHtml(e.project_name)}` : ''}</p>
            ${hasProject && e.imported_question_count > 0 ? `
                <mark>
                    <span class="ok">${e.imported_question_count} in quiz</span>
                </mark>` : ''}
                ${!hasProject
            ? `<button class="btn-sm primary" data-action="create" data-publisher="${pubAttr}" data-exam="${examAttr}">Create Project</button>`
            : `<button class="btn-sm primary" data-action="scrape" data-publisher="${pubAttr}" data-exam="${examAttr}" data-project-id="${e.project_id}">
                           ${e.imported_question_count > 0 ? '↻ Re-scrape' : 'Scrape Questions'}
                       </button>`
        }
        </div>
    `;
}


// ─── URL Discovery ────────────────────────────────────────────────────

function discoverPublisher() {
    if (!currentPublisher) return;
    startDiscovery(currentPublisher);
}

function _refreshDiscoverPublisherBtn() {
    const btn = document.getElementById('discoverPublisherBtn');
    if (!btn) return;
    const busy = !!(activeJobInfo);
    btn.disabled = busy || !currentPublisher;
}

async function startDiscovery(publisher) {
    if (activeJobInfo && activeJobInfo.job_type === 'url_discovery') return;
    try {
        const resp = await fetch('/api/scraper/start_discovery', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ publisher, delay: 1.5 })
        });
        const { job_id } = await resp.json();
        startProgressStream(job_id, 'url_discovery', publisher, `Discovering ${publisher} URLs`, async () => {
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ publisher, exam_name: examName, project_id: projectId, delay: 1.0 })
        });
        const { job_id } = await resp.json();
        startProgressStream(job_id, 'question_scrape', publisher, `Scraping ${examName}`, () => loadExams(publisher));
    } catch (e) {
        alert('Failed to start scrape: ' + e.message);
    }
}

// ─── Progress Stream ──────────────────────────────────────────────────

let activeEventSource = null;
let activeJobInfo = null; // {job_id, job_type, publisher}

function startProgressStream(job_id, job_type, publisher, label, onComplete) {
    if (activeEventSource) activeEventSource.close();

    activeJobInfo = { job_id, job_type, publisher };
    _refreshDiscoverButton();
    _refreshDiscoverPublisherBtn();

    showProgress(label);
    document.getElementById('logBox').innerHTML = '';

    activeEventSource = new EventSource(`/api/scraper/stream/${job_id}`);
    activeEventSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        updateProgress(data);
        if (data.status === 'completed' || data.status === 'failed') {
            activeEventSource.close();
            activeEventSource = null;
            activeJobInfo = null;
            _refreshDiscoverButton();
            _refreshDiscoverPublisherBtn();
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
        activeJobInfo = null;
        _refreshDiscoverButton();
        _refreshDiscoverPublisherBtn();
    };
}

function _refreshDiscoverButton() {
    const btn = document.getElementById('discoverBtn');
    if (!btn) return;
    const discovering = activeJobInfo && activeJobInfo.job_type === 'url_discovery';
    btn.disabled = discovering;
    if (discovering) {
        btn.textContent = 'Discovering...';
    } else {
        const p = cachedPublishers.find(x => x.name === currentPublisher);
        btn.textContent = p && p.url_count ? '↻ Re-discover URLs' : '+ Discover URLs';
    }
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
    document.getElementById('createModal').showModal();
}

function closeModal() {
    document.getElementById('createModal').close();
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
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ link })
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
            headers: { 'Content-Type': 'application/json' },
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
    const dialog = document.getElementById('addPublisherDialog');
    if (dialog.open) {
        dialog.close();
    } else {
        dialog.showModal();
        document.getElementById('publisherUrlInput').focus();
    }
}

async function addPublisher() {
    const raw = document.getElementById('publisherUrlInput').value.trim();
    if (!raw) return;
    const m = raw.match(/\/discussions\/([a-z0-9-]+)/i);
    const name = m ? m[1].toLowerCase() : raw.toLowerCase().replace(/[^a-z0-9-]/g, '');
    if (!name) { alert('Could not parse publisher name from input'); return; }

    document.getElementById('publisherUrlInput').value = '';
    document.getElementById('addPublisherDialog').close();

    await fetch('/api/scraper/publishers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });

    await loadPublishers();
    selectPublisher(name);
}

// ─── Init ─────────────────────────────────────────────────────────────

async function checkRunningJobs() {
    try {
        const resp = await fetch('/api/scraper/running_jobs');
        const jobs = await resp.json();
        if (!jobs.length) return;
        const job = jobs[0];
        const label = job.job_type === 'url_discovery'
            ? `Discovering ${job.publisher} URLs`
            : `Scraping ${job.exam_name}`;
        const onComplete = job.job_type === 'url_discovery'
            ? async () => { await loadPublishers(); if (job.publisher) selectPublisher(job.publisher); }
            : () => { if (job.publisher) loadExams(job.publisher); };
        startProgressStream(job.id, job.job_type, job.publisher, label, onComplete);
    } catch (e) {
        // silently ignore if check fails
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('createModal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });


    loadPublishers();
    checkRunningJobs();
});
