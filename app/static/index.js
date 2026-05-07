let currentProjectId = null;

function checkProgress(projectId, progress) {
    currentProjectId = projectId;
    if (progress > 0) {
        document.getElementById('progressModal').showModal();
    } else {
        window.location.href = '/quiz/' + projectId;
    }
}

function closeModal() {
    document.getElementById('progressModal').close();
    currentProjectId = null;
}

function continueQuiz() {
    window.location.href = '/quiz/' + currentProjectId;
}

async function startNew() {
    try {
        const response = await fetch('/api/reset_progress/' + currentProjectId, { method: 'POST' });
        if (response.ok) {
            window.location.href = '/quiz/' + currentProjectId;
        } else {
            alert('Error resetting progress. Please try again.');
        }
    } catch (error) {
        alert('Error resetting progress. Please try again.');
    }
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('progressModal').addEventListener('click', e => {
        if (e.target === e.currentTarget) closeModal();
    });
});
