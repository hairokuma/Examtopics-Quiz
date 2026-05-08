let questions = [];
let currentQuestionIndex = 0;
let selectedAnswers = new Set();
let navFilter = 'all';

function getFilteredIndices() {
    return questions.reduce((acc, q, i) => {
        if (navFilter === 'all' ||
            (navFilter === 'incorrect' && q.is_correct === 0 && q.answered_at) ||
            (navFilter === 'marked' && q.is_marked === 1)) {
            acc.push(i);
        }
        return acc;
    }, []);
}

function setNavFilter(filter) {
    navFilter = filter;
    document.querySelectorAll('.nav-buttons button').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.filter === filter);
    });
    renderQuestionNav();
}

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

document.addEventListener('DOMContentLoaded', () => {
    loadQuestions();
    updateStats();

    window.addEventListener('popstate', (event) => {
        if (event.state && event.state.questionId) {
            const index = questions.findIndex(q => q.id === event.state.questionId);
            if (index >= 0 && index < questions.length) {
                showQuestion(index);
            }
        }
    });
});


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

    const filteredSet = new Set(getFilteredIndices());

    questions.forEach((question, index) => {
        if (!filteredSet.has(index)) return;

        const navItem = document.createElement('div');
        navItem.className = 'item';
        const navText = document.createElement('p');
        const preview = question.question_text.length > 300
            ? question.question_text.substring(0, 300) + '…'
            : question.question_text;
        navText.textContent = `T${question.topic_id}-Q${question.question_id} ${preview}`;
        navItem.appendChild(navText);

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

        navItem.addEventListener('click', () => showQuestion(index));
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
        if (!/^[A-Z]$/.test(key)) return;
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
        <div class="header">
            <div class="question-number">Topic ${question.topic_id} - Question ${question.question_id} (${currentQuestionIndex + 1} of ${questions.length}) <a href="${safeUrl(question.source_url)}" target="_blank">🔗</a></div>
            <button id="mark-btn" class="btn btn-primary ${question.is_marked ? 'marked' : ''}" 
                onclick="toggleMark(${question.id})">
                ${question.is_marked ? '🔖 Marked' : 'Mark for Review'}
            </button>
        </div>
        
        <p>${processedQuestionText}</p>
        
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
    
    // Render navigation buttons in footer (respects active filter)
    const navButtons = document.getElementById('quiz-footer');
    const filteredIndices = getFilteredIndices();
    const hasPrev = filteredIndices.some(i => i < index);
    const hasNext = filteredIndices.some(i => i > index);
    navButtons.innerHTML = `
        <button class="btn ${!hasPrev ? 'disabled' : 'btn-primary'}"
            onclick="previousQuestion()" ${!hasPrev ? 'disabled' : ''}>
            ← Previous
        </button>
        <button class="btn ${!hasNext ? 'disabled' : 'btn-primary'}"
            onclick="nextQuestion()" ${!hasNext ? 'disabled' : ''}>
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
    const submitBtn = document.querySelector('.btn-success');
    submitBtn.disabled = true;
    submitBtn.classList.add('btn-disabled');
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

        const progressPct = stats.total > 0 ? ` (${Math.round(stats.answered / stats.total * 100)}%)` : '';
        const correctPct = stats.answered > 0 ? ` (${Math.round(stats.correct / stats.answered * 100)}%)` : '';
        document.getElementById('progressStat').textContent = `${stats.answered}/${stats.total}${progressPct}`;
        document.getElementById('correctStat').textContent = `${stats.correct}${correctPct}`;
        document.getElementById('markedStat').textContent = stats.marked;

    } catch (error) {
        console.error('Error updating stats:', error);
    }
}

function previousQuestion() {
    const before = getFilteredIndices().filter(i => i < currentQuestionIndex);
    if (before.length) showQuestion(before[before.length - 1]);
}

function nextQuestion() {
    const after = getFilteredIndices().filter(i => i > currentQuestionIndex);
    if (after.length) showQuestion(after[0]);
}
