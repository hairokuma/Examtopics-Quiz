let questions = [];
let currentQuestionIndex = 0;
let selectedAnswers = new Set();

// Get URL parameter by name
function getUrlParameter(name) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(name);
}

// Update URL with current question
function updateUrl(questionId) {
    const newUrl = `/quiz/${projectId}/question/${questionId}`;
    window.history.pushState({ questionId }, '', newUrl);
}

// Load questions on page load
document.addEventListener('DOMContentLoaded', () => {
    loadQuestions();
    updateStats();
    initToggleSidebar();
    checkScreenSize();
    window.addEventListener('resize', checkScreenSize);
    
    // Handle browser back/forward buttons
    window.addEventListener('popstate', (event) => {
        if (event.state && event.state.questionId) {
            const index = questions.findIndex(q => q.id === event.state.questionId);
            if (index >= 0 && index < questions.length) {
                showQuestion(index);
            }
        }
    });
});

// Check screen size and hide sidebar on mobile
function checkScreenSize() {
    const questionList = document.getElementById('questionList');
    const toggleBtn = document.getElementById('toggleSidebar');
    
    if (questionList && toggleBtn) {
        if (window.innerWidth <= 768) {
            questionList.classList.add('hidden');
            toggleBtn.classList.add('sidebar-hidden');
            toggleBtn.textContent = '☰';
        } else {
            questionList.classList.remove('hidden');
            toggleBtn.classList.remove('sidebar-hidden');
            toggleBtn.textContent = '✕';
        }
    }
}

// Toggle sidebar functionality
function initToggleSidebar() {
    const toggleBtn = document.getElementById('toggleSidebar');
    const questionList = document.getElementById('questionList');
    // const quizContainer = document.querySelector('.quiz-container');
    
    if (toggleBtn && questionList) {
        toggleBtn.addEventListener('click', () => {
            questionList.classList.toggle('hidden');
            toggleBtn.classList.toggle('sidebar-hidden');
            // quizContainer.classList.toggle('sidebar-hidden');
            
            // Update button icon
            if (questionList.classList.contains('hidden')) {
                toggleBtn.textContent = '☰';
            } else {
                toggleBtn.textContent = '✕';
            }
        });
    }
}

// Process text to detect and convert image URLs to img tags
function processTextWithImages(text) {
    if (!text) return '';
    
    // Regex patterns to detect various image URL formats
    const imageUrlPattern = /(https?:\/\/[^\s<>"]+?\.(jpg|jpeg|png|gif|bmp|webp|svg)(\?[^\s<>"]*)?)/gi;
    const markdownImagePattern = /!\[([^\]]*)\]\(([^)]+)\)/g;
    
    // First, handle markdown image syntax ![alt](url)
    text = text.replace(markdownImagePattern, (match, alt, url) => {
        return `<div class="embedded-image"><img src="${url}" alt="${alt}" /></div>`;
    });
    
    // Then handle plain URLs
    text = text.replace(imageUrlPattern, (match) => {
        return `<div class="embedded-image"><img src="${match}" alt="Question image" /></div>`;
    });
    
    return text;
}

async function loadQuestions() {
    try {
        const response = await fetch(`/api/questions/${projectId}`);
        questions = await response.json();
        
        if (questions.length === 0) {
            document.getElementById('questionContent').innerHTML = 
                '<div class="loading">No questions available for this project.</div>';
            return;
        }
        
        renderQuestionNav();
        
        // Check URL for question parameter
        const urlPath = window.location.pathname;
        const questionMatch = urlPath.match(/\/question\/(\d+)/);
        let startIndex = 0;
        
        if (questionMatch) {
            const questionId = parseInt(questionMatch[1]);
            startIndex = questions.findIndex(q => q.id === questionId);
            if (startIndex < 0 || startIndex >= questions.length) {
                startIndex = 0;
            }
        }
        
        showQuestion(startIndex);
    } catch (error) {
        console.error('Error loading questions:', error);
        document.getElementById('questionContent').innerHTML = 
            '<div class="loading">Error loading questions. Please try again.</div>';
    }
}

function renderQuestionNav() {
    const navContainer = document.getElementById('questionNav');
    navContainer.innerHTML = '';
    
    questions.forEach((question, index) => {
        const navItem = document.createElement('div');
        navItem.className = 'question-nav-item';
      navItem.textContent = `T${question.topic_id}-Q${question.question_id} ${question.question_text.substring(0, 30)}...`;
      // navItem.title = ;
        
        if (question.is_correct === 1) {
            navItem.classList.add('correct');
        } else if (question.is_correct === 0 && question.answered_at) {
            navItem.classList.add('incorrect');
        }
        
        if (question.is_marked === 1) {
            navItem.classList.add('marked');
        }
        
        if (index === currentQuestionIndex) {
            navItem.classList.add('active');
        }
        
        navItem.onclick = () => showQuestion(index);
        navContainer.appendChild(navItem);
    });
}

function showQuestion(index) {
    currentQuestionIndex = index;
    const question = questions[index];
    selectedAnswers.clear();
    
    // Update URL with current question id
    updateUrl(question.id);
    
    const contentDiv = document.getElementById('questionContent');
    
    // Process question text to extract and display images
    const processedQuestionText = processTextWithImages(question.question_text);
    
    // Build answers HTML
    let answersHTML = '';
    const answerKeys = Object.keys(question.answers).sort();
    
    answerKeys.forEach(key => {
        const processedAnswerText = processTextWithImages(question.answers[key]);
        answersHTML += `
            <label class="answer-option" for="answer-${key}">
                <input type="checkbox" id="answer-${key}" value="${key}" 
                    onchange="toggleAnswer('${key}')">
                <span class="answer-label">
                    <span class="answer-key">${key}.</span>
                    <span class="answer-text">${processedAnswerText}</span>
                </span>
            </label>
        `;
    });
    
    contentDiv.innerHTML = `
        <div class="question-header">
            <div class="question-number">Topic ${question.topic_id} - Question ${question.question_id} (${currentQuestionIndex + 1} of ${questions.length}) <a href="${question.source_url}" target="_blank">🔗</a></div>
            <button id="mark-btn" class="btn btn-primary ${question.is_marked ? 'marked' : ''}" 
                onclick="toggleMark(${question.id})">
                ${question.is_marked ? '🔖 Marked' : 'Mark for Review'}
            </button>
        </div>
        
        <div class="question-text">${processedQuestionText}</div>
        
        <div class="answers-container">
            ${answersHTML}
        </div>
        
        <div class="answer-actions">
            <button class="btn btn-success" onclick="submitAnswer()">
                Submit Answer
            </button>
            <div id="feedback"></div>
        </div>
        
    `;
    
    // Render navigation buttons in footer
  const navButtons = document.getElementById('quiz-footer');
    navButtons.innerHTML = `
        <button class="btn ${index === 0 ? 'disabled' : 'btn-primary'}" 
            onclick="previousQuestion()" ${index === 0 ? 'disabled' : ''}>
            ← Previous
        </button>
        <button class="btn ${index === questions.length - 1 ? 'disabled' : 'btn-primary'}" 
            onclick="nextQuestion()" ${index === questions.length - 1 ? 'disabled' : ''}>
            Next →
        </button>
    `;
    
    renderQuestionNav();
}

function toggleAnswer(key) {
    const checkbox = document.getElementById(`answer-${key}`);
    const label = checkbox.closest('.answer-option');
    
    if (checkbox.checked) {
        selectedAnswers.add(key);
        label.classList.add('selected');
    } else {
        selectedAnswers.delete(key);
        label.classList.remove('selected');
    }
}

async function submitAnswer() {
    if (selectedAnswers.size === 0) {
        alert('Please select at least one answer');
        return;
    }
    
    const question = questions[currentQuestionIndex];
    const userAnswers = Array.from(selectedAnswers).sort();
    
    try {
        const response = await fetch('/api/submit_answer', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                question_id: question.id,
                user_answers: userAnswers
            })
        });
        
        const result = await response.json();
        displayFeedback(result);
        
        // Update question data
        questions[currentQuestionIndex].is_correct = result.correct ? 1 : 0;
        questions[currentQuestionIndex].user_answer_keys = userAnswers;
        
        // Update stats
        updateStats();
        renderQuestionNav();
        
    } catch (error) {
        console.error('Error submitting answer:', error);
        alert('Error submitting answer. Please try again.');
    }
}

function displayFeedback(result) {
    const feedbackDiv = document.getElementById('feedback');
    const answerKeys = Object.keys(questions[currentQuestionIndex].answers).sort();
    
    if (result.correct) {
        feedbackDiv.innerHTML = `
        ✅ Correct! Well done!`;
    } else {
        feedbackDiv.innerHTML = `
        ❌ Incorrect. The correct answer${result.correct_answers.length > 1 ? 's are' : ' is'}: ${result.correct_answers.join(', ')}`;
    }
    
    // Highlight correct and incorrect answers
    answerKeys.forEach(key => {
        const label = document.querySelector(`#answer-${key}`).closest('.answer-option');
        
        if (result.correct_answers.includes(key)) {
            label.classList.add('correct-answer');
        }
        
        if (result.user_answers.includes(key) && !result.correct_answers.includes(key)) {
            label.classList.add('wrong-answer');
        }
        
        // Disable further changes
        document.querySelector(`#answer-${key}`).disabled = true;
    });
    
    // Disable submit button
    document.querySelector('.btn-success').disabled = true;
    document.querySelector('.btn-success').style.opacity = '0.5';
    document.querySelector('.btn-success').style.cursor = 'not-allowed';
}

async function toggleMark(questionId) {    
    try {
        const response = await fetch(`/api/toggle_mark/${questionId}`, {
            method: 'POST'
        });
        
        const result = await response.json();
        questions[currentQuestionIndex].is_marked = result.is_marked;
        
        const markBtn = document.getElementById('mark-btn');
        if (result.is_marked) {
            markBtn.classList.add('marked');
            markBtn.textContent = '🔖 Marked';
        } else {
            markBtn.classList.remove('marked');
            markBtn.textContent = 'Mark for Review';
        }
        
        updateStats();
        renderQuestionNav();
        
    } catch (error) {
        console.error('Error toggling mark:', error);
    }
}

async function updateStats() {
    try {
        const response = await fetch(`/api/stats/${projectId}`);
        const stats = await response.json();
        
        document.getElementById('progressStat').textContent = 
            `${stats.answered}/${stats.total}`;
        document.getElementById('correctStat').textContent = stats.correct;
        document.getElementById('markedStat').textContent = stats.marked;
        
    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

function previousQuestion() {
    if (currentQuestionIndex > 0) {
        showQuestion(currentQuestionIndex - 1);
    }
}

function nextQuestion() {
    if (currentQuestionIndex < questions.length - 1) {
        showQuestion(currentQuestionIndex + 1);
    }
}
