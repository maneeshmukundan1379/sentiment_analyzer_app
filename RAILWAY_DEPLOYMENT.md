# Railway Deployment Guide

This guide explains how to host the Sentiment Analyzer app on Railway so it can run without any dependency on your local machine.

## What Railway Will Host

The app has two parts:

- Backend: the FastAPI API that performs searches and generates PDFs.
- Frontend: the React web page users open in the browser.

On Railway, deploy these as two separate services from the same GitHub repository.

## Before You Start

Make sure your project is pushed to GitHub.

Do not commit or upload secret files such as:

- `.env`
- `sentiment_analyzer_env.sqlite3`
- any file containing API keys

Railway will store the API keys securely as environment variables.

## Backend Service

1. Open Railway.
2. Click `New Project`.
3. Choose `Deploy from GitHub repo`.
4. Select the repository that contains this app.
5. Set the service root directory to:

```text
agents/2_openai/sentiment_analyzer_app
```

6. Set the backend build command:

```bash
pip install -r requirements.txt
```

7. Set the backend start command:

```bash
uvicorn app:app --host 0.0.0.0 --port $PORT
```

## Backend Environment Variables

In the Railway backend service, open `Variables` and add these values:

```text
GEMINI_API_KEY=your_gemini_api_key
GOOGLE_API_KEY=your_google_api_key
GEMINI_MODEL=gemini-3.1-flash-lite-preview
GEMINI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai/
X_BEARER_TOKEN=your_x_bearer_token
X_API_BASE_URL=https://api.x.com/2
SERPER_API_KEY=your_serper_api_key
```

After the frontend is deployed, also add this backend variable:

```text
CORS_ORIGINS=https://your-frontend-url.up.railway.app
```

Replace `https://your-frontend-url.up.railway.app` with the actual Railway URL of your frontend service.

## Frontend Service

1. In the same Railway project, create another service.
2. Choose the same GitHub repository.
3. Set the frontend service root directory to:

```text
agents/2_openai/sentiment_analyzer_app/frontend
```

4. Set the frontend build command:

```bash
npm install && npm run build
```

5. Set the frontend start command:

```bash
npm run preview -- --host 0.0.0.0 --port $PORT
```

## Frontend Environment Variable

In the Railway frontend service, open `Variables` and add:

```text
VITE_API_BASE_URL=https://your-backend-url.up.railway.app
```

Replace `https://your-backend-url.up.railway.app` with the actual Railway URL of your backend service.

## Final Deployment Steps

1. Redeploy the backend service.
2. Redeploy the frontend service.
3. Open the frontend Railway URL in your browser.
4. Search for a keyword, such as `OptioRx`.
5. Confirm that search results appear.
6. Generate a PDF to confirm PDF export works.

## Important Notes

- Railway environment variables replace local `.env` values.
- The app should not need your local computer once deployed.
- The frontend needs `VITE_API_BASE_URL` so it knows where the backend API is.
- The backend needs `CORS_ORIGINS` so it allows browser requests from the frontend.
- Keep API keys only in Railway variables, not in GitHub.

