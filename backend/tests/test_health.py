from fastapi.testclient import TestClient

from app.main import create_app


def test_health_endpoint_returns_api_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "ai-stock-intelligence-api",
        "environment": "development",
    }


def test_health_endpoint_allows_frontend_origin() -> None:
    client = TestClient(create_app())

    response = client.get("/health", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
