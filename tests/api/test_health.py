"""Route /health : vivacité sans I/O externe."""

from fastapi.testclient import TestClient

from app.main import app


def test_health_repond_sans_grist():
    client = TestClient(app)  # hors context manager : lifespan non exécuté
    reponse = client.get("/health")
    assert reponse.status_code == 200
    corps = reponse.json()
    assert corps["statut"] == "ok"
    assert "version" in corps


def test_docs_desactivees():
    client = TestClient(app)
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
