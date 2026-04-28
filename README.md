# Quiz Learning App

A simple web-based quiz application that helps you learn and practice questions from different projects stored in the `examtopics.db` SQLite database.

## Features

- 📚 **Multiple Projects**: Select from different exam preparation projects
- ✅ **Interactive Quiz**: Select one or multiple answers for each question
- 📊 **Progress Tracking**: Track answered questions, correct answers, and marked questions
- 🔖 **Mark for Review**: Mark difficult questions for later review
- 🎯 **Instant Feedback**: Get immediate feedback on your answers
- 📈 **Statistics Dashboard**: View your progress and performance stats

## Project Structure

```
ET/
├── app.py                 # Flask backend application
├── examtopics.db          # SQLite database with questions
├── requirements.txt       # Python dependencies
├── templates/
│   ├── index.html         # Project selection page
│   └── quiz.html          # Quiz interface page
└── static/
    ├── style.css          # Styling for the application
    └── quiz.js            # JavaScript for quiz functionality
```

## Database Schema

The application uses the following tables from `examtopics.db`:

- **projects**: Contains exam projects with name, description, and question count
- **question_new**: Contains questions with answers, correct answer keys, and user progress

## Installation

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Ensure the database file exists:**
   Make sure `examtopics.db` is in the same directory as `app.py`

## Running the Application

1. **Start the Flask server:**
   ```bash
   cd /mnt/c/Users/fdoelling_ailio/Data/ET && source venv/bin/activate
   python app.py
   ```

2. **Open your web browser and navigate to:**
   ```
   http://localhost:5000
   ```

3. **Select a project** from the main page to start the quiz

## How to Use

1. **Select a Project**: On the home page, choose a project you want to practice
2. **Answer Questions**: 
   - Read the question carefully
   - Select one or more answer options by checking the boxes
   - Click "Submit Answer" to check your response
3. **Navigate**: 
   - Use "Previous" and "Next" buttons to move between questions
   - Click on question numbers in the sidebar for quick navigation
4. **Mark Questions**: Click "Mark for Review" to flag difficult questions
5. **Track Progress**: View your statistics at the top of the quiz page

## Features Explained

### Question States
- **Green**: Correctly answered
- **Red**: Incorrectly answered
- **Yellow bookmark**: Marked for review

### Statistics
- **Progress**: Shows how many questions you've answered out of total
- **Correct**: Number of correctly answered questions
- **Marked**: Number of questions marked for review

## API Endpoints

- `GET /` - Home page with project selection
- `GET /quiz/<project_id>` - Quiz interface for a specific project
- `GET /api/questions/<project_id>` - Get all questions for a project
- `POST /api/submit_answer` - Submit an answer and get feedback
- `POST /api/toggle_mark/<question_id>` - Mark/unmark a question
- `GET /api/stats/<project_id>` - Get statistics for a project

## Technologies Used

- **Backend**: Flask (Python)
- **Database**: SQLite
- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Styling**: Custom CSS with responsive design

## Notes

- All question progress is automatically saved to the database
- You can revisit questions at any time
- The application supports multiple-choice questions with one or more correct answers
- Works on desktop and mobile devices

## License

This is a learning tool for personal use.
✅
⬜