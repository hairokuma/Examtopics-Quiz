function initToggleSidebar() {
    const toggleBtn = document.getElementById('toggleSidebar');
    const nav = document.querySelector('main > nav');
    if (!toggleBtn || !nav) return;

    const syncIcon = () => {
        toggleBtn.textContent = nav.classList.contains('hidden') ? '☰' : '✕';
    };

    const applyScreenSize = () => {
        nav.classList.toggle('hidden', window.innerWidth <= 768);
        syncIcon();
    };

    toggleBtn.addEventListener('click', () => {
        nav.classList.toggle('hidden');
        syncIcon();
    });

    applyScreenSize();
    window.addEventListener('resize', applyScreenSize);
}

document.addEventListener('DOMContentLoaded', initToggleSidebar);

function processTextWithImages(text) {
    if (!text) return '';
    const imageUrlPattern = /(https?:\/\/[^\s<>"]+?\.(jpg|jpeg|png|gif|bmp|webp|svg)(\?[^\s<>"]*)?)/gi;
    const markdownImagePattern = /!\[([^\]]*)\]\(([^)]+)\)/g;
    text = text.replace(markdownImagePattern, (match, alt, url) => {
        return `<div class="embedded-image"><img src="${url}" alt="${alt}" /></div>`;
    });
    text = text.replace(imageUrlPattern, (match) => {
        return `<div class="embedded-image"><img src="${match}" alt="Question image" /></div>`;
    });
    return text;
}

function escapeRegex(string) {
    return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function safeUrl(url) {
    if (!url) return '#';
    const lower = url.toLowerCase().trim();
    if (!lower.startsWith('http://') && !lower.startsWith('https://')) return '#';
    return escapeHtml(url);
}
