'use strict';

let currentProjectId = null;
let currentProject = null;
let editingProjectId = null;
let editingQuestionId = null;
let projectsCache = [];
let questionsCache = {};
let confirmCallback = null;

document.addEventListener('DOMContentLoaded', () => {
    loadProjects();
    _refreshAddQuestionBtn();
    document.getElementById('confirmBtn').addEventListener('click', () => {
        if (confirmCallback) confirmCallback();
    });
});

// ─── Projects ──────────────────────────────────────────────────────────────

async function loadProjects() {
    const container = document.getElementById('projectItems');
    try {
        const res = await fetch('/api/admin/projects');
        projectsCache = await res.json();
        if (!projectsCache.length) {
            container.innerHTML = '<div class="placeholder">No projects</div>';
            return;
        }
        container.innerHTML = projectsCache.map(p => `
            <div class="item${p.id === currentProjectId ? ' active' : ''}" data-id="${p.id}"
                 onclick="selectProject(${p.id}, this)">
                <p>${escapeHtml(p.name)}</p>
                <span>${p.question_count} questions</span>
            </div>
        `).join('');
    } catch {
        container.innerHTML = '<div class="placeholder error">Failed to load</div>';
    }
}

function selectProject(id, el) {
    document.querySelectorAll('#projectItems .item').forEach(i => i.classList.remove('active'));
    el.classList.add('active');
    currentProjectId = id;
    currentProject = projectsCache.find(p => p.id === id) || null;

    if (currentProject) {
        document.getElementById('adminFooter').style.display = '';
        document.getElementById('footerProjectName').textContent = currentProject.name;
    }

    _refreshAddQuestionBtn();
    loadQuestions(id);
}

function _refreshAddQuestionBtn() {
    const btn = document.getElementById('addQuestionBtn');
    if (!btn) return;
    btn.disabled = !currentProjectId;
}

function openProjectDialog(project) {
    editingProjectId = project ? project.id : null;
    document.getElementById('projectDialogTitle').textContent = project ? 'Edit Project' : 'New Project';
    document.getElementById('pdName').value = project?.name || '';
    document.getElementById('pdDescription').value = project?.description || '';
    document.getElementById('pdLink').value = project?.link || '';
    document.getElementById('pdExamName').value = project?.exam_name || '';
    document.getElementById('pdQuestions').value = project?.questions ?? '';
    document.getElementById('pdLastUpdated').value = project?.last_updated_on || '';
    document.getElementById('projectDialog').showModal();
}

async function saveProject() {
    const name = document.getElementById('pdName').value.trim();
    if (!name) { alert('Name is required'); return; }

    const data = {
        name,
        description: document.getElementById('pdDescription').value.trim(),
        link: document.getElementById('pdLink').value.trim(),
        exam_name: document.getElementById('pdExamName').value.trim(),
        questions: parseInt(document.getElementById('pdQuestions').value) || null,
        last_updated_on: document.getElementById('pdLastUpdated').value.trim(),
    };

    const url = editingProjectId ? `/api/admin/projects/${editingProjectId}` : '/api/admin/projects';
    const res = await fetch(url, {
        method: editingProjectId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const result = await res.json();

    if (!res.ok) {
        alert(result.error || 'Failed to save project');
        return;
    }

    document.getElementById('projectDialog').close();
    await loadProjects();

    if (editingProjectId && currentProjectId === editingProjectId) {
        currentProject = projectsCache.find(p => p.id === currentProjectId) || null;
        if (currentProject) document.getElementById('footerProjectName').textContent = currentProject.name;
    }
}

function confirmDeleteProject() {
    if (!currentProject) return;
    document.getElementById('confirmMessage').textContent =
        `Delete "${currentProject.name}"? This will also delete all ${currentProject.question_count} questions.`;
    confirmCallback = async () => {
        const res = await fetch(`/api/admin/projects/${currentProjectId}`, { method: 'DELETE' });
        if (!res.ok) { alert('Failed to delete project'); return; }
        document.getElementById('confirmDialog').close();
        currentProjectId = null;
        currentProject = null;
        document.getElementById('adminFooter').style.display = 'none';
        document.getElementById('questionContent').innerHTML =
            '<div class="placeholder">Select a project to manage questions</div>';
        loadProjects();
    };
    document.getElementById('confirmDialog').showModal();
}

// ─── Questions ─────────────────────────────────────────────────────────────

async function loadQuestions(projectId) {
    const content = document.getElementById('questionContent');
    content.innerHTML = '<div class="loading">Loading...</div>';
    try {
        const res = await fetch(`/api/admin/projects/${projectId}/questions`);
        const questions = await res.json();
        questionsCache = {};
        questions.forEach(q => { questionsCache[q.id] = q; });

        if (!questions.length) {
            content.innerHTML = '<div class="placeholder">No questions in this project</div>';
            return;
        }

        content.innerHTML = questions.map(q => `
            <div class="card">
                <div class="header">
                    <h2><mark>T${q.topic_id ?? '?'} · Q${q.question_id ?? '?'}</mark></h2>
                    <div>
                        <button class="btn-sm" onclick="openQuestionDialog(${q.id})">Edit</button>
                        <button class="btn-sm" onclick="confirmDeleteQuestion(${q.id})">Delete</button>
                    </div>
                </div>
                <p>${escapeHtml((q.question_text || '').substring(0, 200))}${(q.question_text || '').length > 200 ? '…' : ''}</p>
            </div>
        `).join('');
    } catch {
        content.innerHTML = '<div class="placeholder error">Failed to load questions</div>';
    }
}

function _answerRowHtml(key, text, isCorrect) {
    return `<div class="answer-row" data-key="${escapeHtml(key)}">
        <b>${escapeHtml(key)}</b>
        <input type="text" value="${escapeHtml(text)}" placeholder="Answer text">
        <input type="checkbox" title="Mark as correct"${isCorrect ? ' checked' : ''}>
    </div>`;
}

function _renderAnswers(answersObj, correctKeys) {
    const container = document.getElementById('qdAnswersContainer');
    const keys = Object.keys(answersObj).sort();
    container.innerHTML = keys.map(k => _answerRowHtml(k, answersObj[k], correctKeys.includes(k))).join('');
}

function addAnswerRow() {
    const container = document.getElementById('qdAnswersContainer');
    const used = new Set([...container.querySelectorAll('.answer-row')].map(r => r.dataset.key));
    const next = [...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].find(l => !used.has(l));
    if (next) container.insertAdjacentHTML('beforeend', _answerRowHtml(next, '', false));
}

function _getAnswersFromDialog() {
    const answerObject = {};
    const correctKeys = [];
    document.getElementById('qdAnswersContainer').querySelectorAll('.answer-row').forEach(row => {
        const key = row.dataset.key;
        const text = row.querySelector('input[type="text"]').value.trim();
        const correct = row.querySelector('input[type="checkbox"]').checked;
        if (key && text) {
            answerObject[key] = text;
            if (correct) correctKeys.push(key);
        }
    });
    return { answerObject, correctKeys };
}

function openQuestionDialog(questionId) {
    editingQuestionId = questionId;
    document.getElementById('questionDialogTitle').textContent = questionId ? 'Edit Question' : 'New Question';
    if (questionId) {
        const q = questionsCache[questionId];
        document.getElementById('qdTopicId').value = q.topic_id ?? '';
        document.getElementById('qdQuestionId').value = q.question_id ?? '';
        document.getElementById('qdQuestionText').value = q.question_text || '';
        _renderAnswers(JSON.parse(q.answer_object || '{}'), JSON.parse(q.correct_answer_keys || '[]'));
    } else {
        document.getElementById('qdTopicId').value = '';
        document.getElementById('qdQuestionId').value = '';
        document.getElementById('qdQuestionText').value = '';
        _renderAnswers({}, []);
    }
    document.getElementById('questionDialog').showModal();
}

async function saveQuestion() {
    const { answerObject, correctKeys } = _getAnswersFromDialog();
    if (!Object.keys(answerObject).length) {
        alert('At least one answer option is required');
        return;
    }

    const data = {
        topic_id: parseInt(document.getElementById('qdTopicId').value) || null,
        question_id: parseInt(document.getElementById('qdQuestionId').value) || null,
        question_text: document.getElementById('qdQuestionText').value,
        answer_object: JSON.stringify(answerObject),
        correct_answer_keys: JSON.stringify(correctKeys),
    };

    const url = editingQuestionId
        ? `/api/admin/questions/${editingQuestionId}`
        : `/api/admin/projects/${currentProjectId}/questions`;
    const res = await fetch(url, {
        method: editingQuestionId ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
    });
    const result = await res.json();

    if (!res.ok) {
        alert(result.error || 'Failed to save question');
        return;
    }

    document.getElementById('questionDialog').close();
    loadQuestions(currentProjectId);
}

async function deletePublisher() {
    if (!currentProject) return;

    let info;
    try {
        const res = await fetch(`/api/admin/projects/${currentProjectId}/publisher`);
        if (!res.ok) {
            const err = await res.json();
            alert(err.error || 'No publisher found for this project');
            return;
        }
        info = await res.json();
    } catch {
        alert('Failed to look up publisher');
        return;
    }

    document.getElementById('confirmMessage').textContent =
        `Delete publisher "${info.publisher}"? This will permanently delete ${info.project_count} projects, ` +
        `${info.question_count} questions, and ${info.url_count} discovered URLs across ${info.exam_count} exam(s).`;
    confirmCallback = async () => {
        const res = await fetch(`/api/admin/publishers/${encodeURIComponent(info.publisher)}`, { method: 'DELETE' });
        if (!res.ok) { alert('Failed to delete publisher'); return; }
        document.getElementById('confirmDialog').close();
        currentProjectId = null;
        currentProject = null;
        document.getElementById('adminFooter').style.display = 'none';
        document.getElementById('questionContent').innerHTML =
            '<div class="placeholder">Select a project to manage questions</div>';
        loadProjects();
    };
    document.getElementById('confirmDialog').showModal();
}

function confirmDeleteQuestion(questionId) {
    const q = questionsCache[questionId];
    document.getElementById('confirmMessage').textContent =
        `Delete T${q.topic_id ?? '?'} Q${q.question_id ?? '?'}?`;
    confirmCallback = async () => {
        const res = await fetch(`/api/admin/questions/${questionId}`, { method: 'DELETE' });
        if (!res.ok) { alert('Failed to delete question'); return; }
        document.getElementById('confirmDialog').close();
        loadQuestions(currentProjectId);
    };
    document.getElementById('confirmDialog').showModal();
}
