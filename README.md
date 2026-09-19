# DataLens AI

> AI-Powered Data & Document Analysis — Portfolio Project

DataLens AI is a web application that allows users to upload CSV, XLSX, PDF, and DOCX files and receive automatic insights, charts, and AI-powered answers.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React, JavaScript, Recharts |
| Backend | Python, FastAPI, Pydantic |
| Data Processing | Pandas, NumPy |
| Database | PostgreSQL, SQLAlchemy |
| AI / RAG | LLM API, FAISS/Chroma |
| DevOps | Docker, Git |

---

## Current Status

🚧 **Project foundation — work in progress.**

Only the project structure has been created. No features are implemented yet.

---

## Project Structure

```
DataLens-AI/
├── frontend/          # React application (Step 4)
├── backend/
│   ├── app/
│   │   ├── api/       # Route handlers
│   │   ├── models/    # Database models
│   │   ├── schemas/   # Pydantic schemas
│   │   ├── services/  # Business logic
│   │   ├── database/  # DB connection & config
│   │   └── main.py    # FastAPI entry point
│   └── tests/         # Backend tests
├── data/
│   └── uploads/       # User-uploaded files (git-ignored)
├── docs/              # Project documentation
├── .env.example       # Environment variable template
├── docker-compose.yml # Container config (future)
└── README.md
```

---

## How to Run (coming in Step 3 & 4)

Instructions for running the backend and frontend will be added after those steps are complete.

---

## Setup

```bash
# Clone the repository
git clone <repo-url>
cd DataLens-AI

# Copy environment config
cp .env.example .env
# Edit .env with your actual values
```
