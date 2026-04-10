from fastapi.testclient import TestClient

from api.server import app


def test_health_and_stats_endpoints():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        stats = client.get("/stats")
        assert stats.status_code == 200
        assert "connected_clients" in stats.json()


def test_websocket_ping_pong():
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as websocket:
            websocket.send_text("ping")
            response = websocket.receive_text()
            assert response == "pong"
