let currentProjectId = null;

function checkProgress(projectId, progress) {
    currentProjectId = projectId;
    if (progress > 0) {
        document.getElementById('progressModal').classList.add('open');
    } else {
        window.location.href = '/quiz/' + projectId;
    }
}

function closeModal() {
    document.getElementById('progressModal').classList.remove('open');
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
        console.error('Error:', error);
        alert('Error resetting progress. Please try again.');
    }
}

window.onclick = function(event) {
    const modal = document.getElementById('progressModal');
    if (event.target === modal) closeModal();
};
