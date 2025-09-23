import pytest
import asyncio
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    """Test health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "timestamp" in data
    assert data["service"] == "ai-news-summarizer"


def test_trigger_news_workflow():
    """Test triggering news workflow."""
    response = client.post("/news/run")
    assert response.status_code == 200
    data = response.json()
    assert "job_id" in data
    assert data["status"] == "started"
    assert "stream_url" in data


def test_list_jobs():
    """Test listing jobs."""
    response = client.get("/news/jobs")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)