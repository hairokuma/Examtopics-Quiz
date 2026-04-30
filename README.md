# Quiz Learning App

A web-based quiz application for practising exam questions scraped from ExamTopics and stored in an SQLite database.

demo: https://examtopics-quiz.ddns.net/

## Features

- Multiple exam projects with progress tracking
- Interactive quiz with single and multi-answer support
- Mark questions for review
- Instant answer feedback with correct-answer highlighting
- Statistics dashboard (progress, correct, marked)
- Full-text search across all questions and answers
- Integrated scraper UI to discover and import new exams

## Project Structure

```
├── app/
│   ├── app.py                 # Flask backend
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── data/
│   │   └── examtopics.db      # SQLite database
│   ├── static/
│   │   ├── style.css          # Shared styles (layout, modal, quiz)
│   │   ├── search.css         # Search page styles
│   │   ├── scraper.css        # Scraper page styles
│   │   ├── utils.js           # Shared utilities (image processing, escaping)
│   │   ├── quiz.js            # Quiz page logic
│   │   ├── index.js           # Home page logic
│   │   ├── search.js          # Search page logic
│   │   └── scraper.js         # Scraper page logic
│   └── templates/
│       ├── index.html         # Project selection
│       ├── quiz.html          # Quiz interface
│       ├── search.html        # Search interface
│       └── scraper.html       # Scraper management
└── config/
    ├── init.sql               # Database seed data
    ├── scraper.py             # Standalone scraper script
    ├── sort_urls.py           # URL organiser utility
    └── getURLbyPublisher.py   # URL discovery utility
```

## Database Schema

- **projects** — exam projects (name, description, question count, link)
- **questions** — imported questions with answers, correct keys, and user progress
- **questions_scraped** — staging table for scraped questions before import
- **discovered_urls** — URLs collected during scraper discovery phase
- **publishers** — publisher entries (e.g. microsoft, databricks)
- **scrape_jobs** — background job status and log for the scraper UI

## Installation

```bash
pip install -r app/requirements.txt
```

## Running

```bash
python app/app.py
# open http://localhost:5000
```

Or with Docker:

```bash
docker compose up
# open http://localhost:5012
```

Read logs: `docker logs examtopics-quiz`

## How to Use

1. **Select a project** on the home page → start or continue a quiz
2. **Answer questions** — select one or more options, click Submit
3. **Navigate** with Previous / Next or the sidebar question list
4. **Mark** difficult questions with the Mark for Review button
5. **Search** across all questions from the home page or within a project

## Question States

| Colour | Meaning |
|--------|---------|
| Green  | Correctly answered |
| Red    | Incorrectly answered |
| Yellow dot | Marked for review |

## API Endpoints

### Quiz
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Home page |
| GET | `/quiz/<project_id>` | Quiz for a project |
| GET | `/search[/<project_id>]` | Search page |
| GET | `/api/questions/<project_id>` | All questions for a project |
| POST | `/api/submit_answer` | Submit answer, get feedback |
| POST | `/api/toggle_mark/<question_id>` | Toggle mark flag |
| GET | `/api/stats/<project_id>` | Progress statistics |
| POST | `/api/reset_progress/<project_id>` | Reset all progress |
| GET | `/api/search` | Full-text search (`?q=`, `?project_id=`, `?exclude_case_study=`) |

### Scraper
| Method | Path | Description |
|--------|------|-------------|
| GET | `/scraper` | Scraper UI |
| GET | `/api/scraper/publishers` | List publishers |
| POST | `/api/scraper/publishers` | Add publisher |
| GET | `/api/scraper/exams/<publisher>` | List exams for a publisher |
| POST | `/api/scraper/start_discovery` | Start URL discovery job |
| POST | `/api/scraper/start_scrape` | Start question scrape job |
| GET | `/api/scraper/stream/<job_id>` | SSE stream for job progress |
| POST | `/api/scraper/import/<project_id>` | Import staged questions into quiz |
| POST | `/api/scraper/create_project` | Create a new project |
| POST | `/api/scraper/fetch_project_info` | Fetch metadata from ExamTopics |

## Scraper Workflow

1. Open `/scraper` in the app
2. Add a publisher (e.g. `microsoft`) and click **Discover URLs** — this finds all discussion links for that publisher
3. Once discovery is done, select an exam and click **Create Project** to add it to the quiz
4. Click **Scrape Questions** to fetch and stage question content
5. Click **Import to Quiz** to move staged questions into the live quiz

The scraper runs as a background job with a live progress bar and log. All steps are re-runnable.

**Note: The scraper can only fetch questions that are publicly accessible on ExamTopics. Some exams may have restricted access.**

Most exams do not have all questions available for scraping. If you want all questions for an exam in the Quiz App, you need to purchase the exam on ExamTopics and add the questions manually to the database using, for example, DB Browser for SQLite.


## Technologies

- **Backend**: Flask (Python), SQLite, BeautifulSoup, requests
- **Frontend**: HTML5, CSS3, Vanilla JavaScript

## License

Personal learning tool.
