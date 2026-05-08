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
    const images = [];

    // Extract patterns into safe img HTML, replacing with indexed tokens
    text = text.replace(markdownImagePattern, (match, alt, url) => {
        const i = images.length;
        images.push(`<div class="embedded-image"><img src="${escapeHtml(url)}" alt="${escapeHtml(alt)}" /></div>`);
        return `\x00${i}\x00`;
    });
    text = text.replace(imageUrlPattern, (match) => {
        const i = images.length;
        images.push(`<div class="embedded-image"><img src="${escapeHtml(match)}" alt="Question image" /></div>`);
        return `\x00${i}\x00`;
    });

    // Escape all non-image text, then splice images back in
    return text.split(/\x00(\d+)\x00/).map((part, i) =>
        i % 2 === 0 ? escapeHtml(part) : images[parseInt(part)]
    ).join('');
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
