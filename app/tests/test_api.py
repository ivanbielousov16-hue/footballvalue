"""Smoke-тести API через TestClient."""
import os
import tempfile

# Використовуємо окрему тимчасову БД для тестів.
_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["FV_DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app.database.db import init_db  # noqa: E402

# TestClient без контекстного менеджера не викликає startup-подію,
# тому створюємо таблиці явно.
init_db()

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_leagues_present():
    r = client.get("/api/leagues")
    assert r.status_code == 200
    assert len(r.json()) > 0


def test_list_matches_and_analyze():
    r = client.get("/api/matches", params={"date_filter": "next7"})
    assert r.status_code == 200
    matches = r.json()
    assert len(matches) > 0
    mid = matches[0]["id"]

    # аналіз матчу
    r2 = client.post(f"/api/matches/{mid}/analyze")
    assert r2.status_code == 200
    body = r2.json()
    assert "predictions" in body
    assert "data_quality" in body
    assert len(body["predictions"]) > 0


def test_manual_odds_and_ev():
    r = client.get("/api/matches", params={"date_filter": "next7"})
    mid = r.json()[0]["id"]
    # додаємо коефіцієнт
    payload = {"match_id": mid, "market": "over_2.5", "decimal_odds": 5.0, "bookmaker": "1win"}
    r2 = client.post("/api/odds/manual", json=payload)
    assert r2.status_code == 200
    # аналіз має врахувати цей коефіцієнт і дати EV
    r3 = client.post(f"/api/matches/{mid}/analyze")
    preds = {p["market"]: p for p in r3.json()["predictions"]}
    assert preds["over_2.5"]["decimal_odds"] == 5.0
    assert preds["over_2.5"]["ev"] is not None


def test_paste_endpoint():
    text = "Arsenal — Chelsea\nТотал більше 2.5\nКоефіцієнт 1.85"
    r = client.post("/api/odds/paste", json={"text": text})
    assert r.status_code == 200
    assert "added" in r.json()


def test_analyze_all_tabs():
    r = client.post("/api/analyze-all", params={"date_filter": "next3"})
    assert r.status_code == 200
    body = r.json()
    assert "tabs" in body
    assert "accumulators" in body
    for tab in ("best", "totals", "btts", "match_result", "skip"):
        assert tab in body["tabs"]


def test_accumulator_build():
    r = client.post("/api/accumulator/build", json={"mode": "balanced", "date_filter": "next3"})
    assert r.status_code == 200
    body = r.json()
    assert "legs" in body
    assert "combined_odds" in body


def test_bankroll_flow():
    client.post("/api/bankroll/txn", json={"kind": "deposit", "amount": 1000})
    r = client.get("/api/bankroll")
    assert r.json()["balance"] >= 1000
