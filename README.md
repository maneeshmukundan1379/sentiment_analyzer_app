# Sentiment Analyzer App

## Overview
`Sentiment Analyzer App` is a React + FastAPI version of the original Gradio workflow.  
It keeps the same core features:
- Keyword textbox
- Results textarea (`Matching Social Posts and Comments`)
- PDF section to create and download the report

The backend reuses the existing search orchestration and PDF generation logic.

## Project Structure
- `app.py`: FastAPI backend entrypoint (`/api/search`, `/api/pdf`, `/api/pdf/download/{report_id}`)
- `logic.py`: Search orchestration used by the API
- `core/`, `platform_agents/`, `social_agents.py`: Existing data collection, enrichment, and PDF/report modules
- `frontend/`: React (Vite) client UI

## Requirements
- Python `3.10+`
- Node.js `18+`
- API key in `GEMINI_API_KEY` or `GOOGLE_API_KEY`
- Optional: `X_BEARER_TOKEN` for more reliable X.com results

## Optional Environment Settings
Create a `.env` file in this directory:

```env
GEMINI_API_KEY=your_api_key_here
# Optional:
# GOOGLE_API_KEY=your_api_key_here
# GEMINI_MODEL=gemini-3.1-flash-lite-preview
# GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
# X_BEARER_TOKEN=your_x_bearer_token_here
# X_API_BASE_URL=https://api.x.com/2
# SOCIAL_LOOKBACK_DAYS=7
# FACEBOOK_GROUP_PAGES=5
# CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
```

## Run Backend API
```bash
cd /Users/maneeshmukundan/projects/agents/2_openai/sentiment_analyzer_app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

## Run React Frontend
```bash
cd /Users/maneeshmukundan/projects/agents/2_openai/sentiment_analyzer_app/frontend
npm install
npm run dev
```

Frontend defaults to calling `http://127.0.0.1:8000`.  
To override, set:

```bash
VITE_API_BASE_URL=http://your-api-host:8000
```

## API Endpoints
- `GET /api/health`
- `POST /api/search` with `{ "keyword": "openai" }`
- `POST /api/pdf` with `{ "records_payload": "...", "searched_keyword": "openai" }`
- `GET /api/pdf/download/{report_id}`
