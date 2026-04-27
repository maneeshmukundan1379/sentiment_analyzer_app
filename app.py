"""
FastAPI entrypoint for Sentiment Analyzer App.
"""

from __future__ import annotations

import os
import re
import tempfile
from uuid import uuid4
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from core.env import load_app_env

load_app_env()

from logic import generate_pdf_report, search_social_keyword


class SearchRequest(BaseModel):
    keyword: str
    platform: str = "All"


class SearchResponse(BaseModel):
    status: str
    results: str
    searched_keyword: str
    records_payload: str


class PdfRequest(BaseModel):
    records_payload: str
    searched_keyword: str = ""


class PdfResponse(BaseModel):
    status: str
    filename: str
    download_url: str


app = FastAPI(title="Sentiment Analyzer App API", version="1.0.0")
GENERATED_REPORTS: dict[str, Path] = {}
FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


def _cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [origin.strip() for origin in configured_origins.split(",") if origin.strip()]


def _report_filename(keyword: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", (keyword or "keyword").strip()).strip("-").lower()
    return f"sentiment-analyzer-{slug or 'keyword'}.pdf"


def _validated_report_path(path: str) -> Path:
    file_path = Path(path).resolve()
    temp_dir = Path(tempfile.gettempdir()).resolve()
    try:
        file_path.relative_to(temp_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid PDF path.") from exc

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="PDF file not found.")
    return file_path

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/search", response_model=SearchResponse)
def search(request: SearchRequest) -> SearchResponse:
    status, results, _cleared_keyword, searched_keyword, records_payload = search_social_keyword(
        request.keyword,
        request.platform,
    )
    return SearchResponse(
        status=status,
        results=results,
        searched_keyword=searched_keyword,
        records_payload=records_payload,
    )


@app.post("/api/pdf", response_model=PdfResponse)
def create_pdf(request: PdfRequest) -> PdfResponse:
    status, pdf_path = generate_pdf_report(request.records_payload, request.searched_keyword)
    if not pdf_path:
        raise HTTPException(status_code=400, detail=status)

    file_path = _validated_report_path(pdf_path)
    report_id = uuid4().hex
    GENERATED_REPORTS[report_id] = file_path
    return PdfResponse(
        status=status,
        filename=_report_filename(request.searched_keyword),
        download_url=f"/api/pdf/download/{report_id}",
    )


@app.get("/api/pdf/download/{report_id}")
def download_pdf(report_id: str) -> FileResponse:
    file_path = GENERATED_REPORTS.get(report_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="PDF report not found.")

    file_path = _validated_report_path(str(file_path))
    return FileResponse(path=file_path, media_type="application/pdf", filename=file_path.name)


if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
