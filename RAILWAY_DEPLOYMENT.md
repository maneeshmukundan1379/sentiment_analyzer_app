# Railway Deployment Guide

This guide explains how to host the Sentiment Analyzer app on Railway so it can run without any dependency on your local machine.

## What Railway Will Host

The app has two parts:

- Backend: the FastAPI API that performs searches and generates PDFs.
- Frontend: the React web page users open in the browser.

On Railway, deploy these together as one service. FastAPI serves both the API and the built React frontend.

## Before You Start

Make sure your project is pushed to GitHub.

Do not commit or upload secret files such as:

- `.env`
- `sentiment_analyzer_env.sqlite3`
- any file containing API keys

Railway will store the API keys securely as environment variables.

## Railway Service

1. Open Railway.
2. Click `New Project`.
3. Choose `Deploy from GitHub repo`.
4. Select the repository that contains this app.
5. Set the service root directory to:

```text
agents/2_openai/sentiment_analyzer_app
```

6. Set the build command:

```bash
pip install -r requirements.txt && cd frontend && npm install && npm run build
```

7. Set the start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

The repository also includes `railway.json` and `Procfile`, so Railway should pick up these commands automatically. If Railway shows a different command, manually set the commands above.

## Environment Variables

In the Railway service, open `Variables` and add these values:

```text
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_google_api_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
X_BEARER_TOKEN=your_x_bearer_token
X_API_BASE_URL=https://api.x.com/2
SERPER_API_KEY=your_serper_api_key
```

Because the frontend and backend are served from the same Railway service, `VITE_API_BASE_URL` is not required.

`CORS_ORIGINS` is usually not required for the single-service setup. If you later host the frontend separately, add:

```text
CORS_ORIGINS=https://your-frontend-url.up.railway.app
```

## Final Deployment Steps

1. Redeploy the Railway service.
2. Open the Railway public URL in your browser.
3. Search for a keyword, such as `OptioRx`.
4. Confirm that search results appear.
5. Generate a PDF to confirm PDF export works.

## Important Notes

- Railway environment variables replace local `.env` values.
- The app should not need your local computer once deployed.
- The React frontend is built into `frontend/dist` during deployment.
- FastAPI serves the built frontend from the same Railway service.
- Keep API keys only in Railway variables, not in GitHub.

