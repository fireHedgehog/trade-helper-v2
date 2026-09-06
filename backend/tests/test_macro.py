"""Macro page: model catalogue + overview / naive composite."""

from __future__ import annotations

import pytest

from app.features.macro import composite


def test_models_endpoint_has_default(client):
    body = client.get("/api/macro/ai-regime/models").json()
    assert body["default"]
    assert any(m["default"] and m["enabled"] for m in body["models"])


def test_budgets_endpoint(client):
    body = client.get("/api/macro/ai-regime/budgets").json()
    keys = {b["key"] for b in body}
    assert keys == {"small", "medium", "large"}
    large = next(b for b in body if b["key"] == "large")
    assert large["rebuttal_round"] is True
    medium = next(b for b in body if b["key"] == "medium")
    small = next(b for b in body if b["key"] == "small")
    assert "macro_catalyst" in medium["personas"]
    assert "macro_catalyst" in large["personas"]
    assert "macro_catalyst" not in small["personas"]


def test_overview_empty(client):
    body = client.get("/api/macro/overview").json()
    assert body["composite"]["score"] is None
    assert body["composite"]["zone"] == "neutral"
    # The category structure is always returned (so the page can render the
    # grid) but every card is empty until a macro fetch runs.
    assert {c["key"] for c in body["categories"]} == {
        "inflation", "rates", "growth", "labor", "risk", "money-fx"
    }
    all_series = [s for c in body["categories"] for s in c["series"]]
    assert all_series and all(s["point_count"] == 0 and s["spark"] == [] for s in all_series)


def test_overview_with_seeded_observations(client):
    # Give a few series enough points for a z-score.
    def rows(series_id, base):
        return [
            (series_id, f"2020-{m:02d}-01", base + i * 0.1)
            for i, m in enumerate(range(1, 13))
        ] + [
            (series_id, f"2021-{m:02d}-01", base + (12 + i) * 0.1)
            for i, m in enumerate(range(1, 13))
        ]

    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("BEGIN")
        # NFCI is scored; DGS2 is intentionally NOT in the composite any more.
        for sid, base in [("VIXCLS", 15.0), ("BAMLH0A0HYM2", 3.0), ("NFCI", -0.4)]:
            conn.executemany(
                "INSERT INTO macro_observations (series_id, date, value) VALUES (?,?,?)",
                rows(sid, base),
            )
            conn.execute(
                """INSERT INTO macro_obs_stats (series_id, point_count, first_date, last_date, last_value)
                   VALUES (?, 24, '2020-01-01', '2021-12-01', ?)""",
                (sid, base + 23 * 0.1),
            )
        conn.execute("COMMIT")

    body = client.get("/api/macro/overview").json()
    assert body["composite"]["score"] is not None
    assert 0 <= body["composite"]["score"] <= 100
    assert body["composite"]["n_used"] >= 3
    risk_cat = next(c for c in body["categories"] if c["key"] == "risk")
    vix = next(s for s in risk_cat["series"] if s["series_id"] == "VIXCLS")
    assert len(vix["spark"]) == 10
    assert vix["composite_sign"] == -1


@pytest.mark.parametrize(
    "score,zone",
    [(10, "risk-off"), (50, "neutral"), (85, "risk-on")],
)
def test_zone_thresholds(score, zone):
    assert composite._zone(score) == zone


def test_next_release_rolls_forward_to_future():
    # A monthly series whose last obs is a year ago → estimate must be in the future.
    est, days = composite.next_release_estimate("Monthly", "2024-01-01", 14)
    assert est is not None
    assert days is not None and days >= 0


def test_qualified_fred_frequencies_preserve_monthly_horizons(client):
    from datetime import date, timedelta
    from app.db.connection import get_connection
    from app.features.macro.ai_regime.snapshot import _macro_features

    cases = [
        ("BAMLH0A0HYM2", "Daily, Close", "Daily", [100.0] * 21 + [99.0, 99.1], 1),
        ("WALCL", "Weekly, As of Wednesday", "Weekly", [100.0] * 3 + [99.0, 99.1], 7),
        ("PCEPILFE", "Monthly", "Monthly", [100.0] * 12 + [101.0], 30),
    ]
    with get_connection() as conn:
        for sid, qualified, plain, values, spacing in cases:
            conn.execute("UPDATE macro_series_catalog SET frequency=? WHERE series_id=?", (qualified, sid))
            conn.executemany("INSERT INTO macro_observations (series_id,date,value) VALUES (?,?,?)", [
                (sid, (date(2020, 1, 1) + timedelta(days=i * spacing)).isoformat(), v)
                for i, v in enumerate(values)])
        qualified, _ = _macro_features(conn)
        assert qualified["BAMLH0A0HYM2"]["d1m_abs"] == pytest.approx(-0.9)
        assert qualified["WALCL"]["d1m_pct"] == pytest.approx(-0.9)
        assert qualified["PCEPILFE"]["d1m_pct"] == pytest.approx(1.0)
        for sid, _, plain, _, _ in cases:
            conn.execute("UPDATE macro_series_catalog SET frequency=? WHERE series_id=?", (plain, sid))
        normalized, _ = _macro_features(conn)
        for sid, *_ in cases:
            assert normalized[sid] == qualified[sid]


def test_frequency_qualifiers_do_not_extend_staleness_or_release_period(client):
    from datetime import date, timedelta
    from app.db.connection import get_connection
    from app.features.macro.ai_regime.runner import _stale_series

    last = (date.today() - timedelta(days=20)).isoformat()
    with get_connection() as conn:
        conn.execute("UPDATE macro_series_catalog SET frequency='Daily, Close', typical_lag_days=1 WHERE series_id='VIXCLS'")
        conn.execute("INSERT INTO macro_obs_stats (series_id,point_count,last_date) VALUES ('VIXCLS',100,?)", (last,))
        assert 'VIXCLS' in _stale_series(conn)
        conn.execute("UPDATE macro_series_catalog SET frequency='Daily' WHERE series_id='VIXCLS'")
        assert 'VIXCLS' in _stale_series(conn)
    for qualified, plain in [('Daily, Close', 'Daily'), ('Weekly, As of Wednesday', 'Weekly')]:
        assert composite.next_release_estimate(qualified, last, 1) == composite.next_release_estimate(plain, last, 1)


def _seed_macro(n_points: int = 30):
    from app.db.connection import get_connection

    with get_connection() as conn:
        conn.execute("BEGIN")
        for sid, base in [
            ("VIXCLS", 15.0), ("BAMLH0A0HYM2", 3.0), ("DGS2", 4.0), ("DGS10", 4.3),
            ("T10Y2Y", 0.3), ("NFCI", -0.4), ("CPILFESL", 300.0), ("PAYEMS", 155000.0),
        ]:
            rows = [
                (sid, f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}", base + i * 0.01)
                for i in range(n_points)
            ]
            conn.executemany(
                "INSERT OR REPLACE INTO macro_observations (series_id, date, value) VALUES (?,?,?)",
                rows,
            )
            conn.execute(
                "INSERT OR REPLACE INTO macro_obs_stats (series_id, point_count, first_date, "
                "last_date, last_value) VALUES (?,?,?,?,?)",
                (sid, n_points, rows[0][1], "2099-01-01", base + (n_points - 1) * 0.01),
            )
        conn.execute("COMMIT")


def test_ai_regime_run_with_stubbed_openai(client, monkeypatch):
    _seed_macro()

    calls: list[str] = []

    async def fake_chat(model, system, user, *, max_tokens, temperature, **kw):
        calls.append(user[:40])
        if "Analyst answers" in user or "Reconcile them" in user:
            body = (
                '{"score":55,"confidence":70,"on_votes":1,"off_votes":1,'
                '"neutral_votes":1,"summary":"Mixed read, leaning neutral because '
                'credit is calm but the curve is flat."}'
            )
        elif "case that the regime is currently risk-ON" in user:
            body = '{"vote":"ON","conviction":80,"key_evidence":["OAS tight"],"rationale":"calm"}'
        elif "case that the regime is currently risk-OFF" in user:
            body = '{"vote":"OFF","conviction":75,"key_evidence":["curve flat"],"rationale":"tight"}'
        else:
            body = '{"vote":"NEUTRAL","conviction":60,"key_evidence":["x"],"rationale":"balanced"}'
        return body, 100, 40

    monkeypatch.setattr("app.features.macro.ai_regime.runner.chat", fake_chat)

    r = client.post("/api/macro/ai-regime/run", json={"budget": "small"})
    assert r.status_code == 200, r.text
    run = r.json()

    assert run["status"] == "ok"
    assert run["on_votes"] + run["off_votes"] + run["neutral_votes"] == 4
    assert 0 <= run["score"] <= 100
    assert 0 <= run["confidence"] <= 100
    assert run["summary"]
    assert run["naive_score"] is not None
    assert len(run["messages"]) == 5  # 4 small-budget personas + reconciler
    assert run["code_weighted_score"] is not None
    assert run["reconciler_score"] is not None
    assert run["weights_json"]
    assert run["messages"][-1]["role"] == "reconciler"

    # cached on the second call
    calls.clear()
    again = client.post("/api/macro/ai-regime/run", json={"budget": "small"}).json()
    assert again["id"] == run["id"]
    assert calls == []  # no new OpenAI calls

    # force re-runs
    forced = client.post(
        "/api/macro/ai-regime/run", json={"budget": "small", "force": True}
    ).json()
    assert forced["id"] == run["id"]  # same trading_date row, upserted
    assert calls  # OpenAI called again


def test_ai_regime_run_without_macro_data_errors(client, monkeypatch):
    async def fake_chat(*a, **k):
        return "{}", 0, 0

    monkeypatch.setattr("app.features.macro.ai_regime.runner.chat", fake_chat)
    r = client.post("/api/macro/ai-regime/run", json={"budget": "small"})
    assert r.status_code == 400
    assert "macro" in r.json()["detail"].lower()


def test_medium_run_applies_separate_bounded_catalyst_overlay(client, monkeypatch):
    from datetime import datetime, timezone

    _seed_macro()

    async def fake_chat(model, system, user, *, max_tokens, temperature, **kw):
        if "Analyst answers" in user:
            body = (
                '{"score":60,"confidence":60,"on_votes":3,"off_votes":2,'
                '"neutral_votes":1,"summary":"Structural regime with a separate catalyst."}'
            )
        else:
            body = '{"vote":"ON","conviction":60,"key_evidence":["x"],"rationale":"x"}'
        return body, 100, 40

    async def fake_web_chat(model, system, user, *, max_tokens, **kw):
        today = datetime.now(timezone.utc).date().isoformat()
        body = (
            '{"vote":"OFF","conviction":80,"impact":4,'
            '"pricing_status":"partly_priced","event":"Hawkish policy surprise",'
            f'"event_date":"{today}","incremental_reason":"Part remains unpriced",'
            '"sources":[{"title":"Source","url":"https://example.com"}]}'
        )
        return body, 120, 50

    monkeypatch.setattr("app.features.macro.ai_regime.runner.chat", fake_chat)
    monkeypatch.setattr("app.features.macro.ai_regime.runner.web_chat", fake_web_chat)

    run = client.post("/api/macro/ai-regime/run", json={"budget": "medium"}).json()
    assert run["event_overlay"] == pytest.approx(-1.6)
    assert run["on_votes"] + run["off_votes"] + run["neutral_votes"] == 6
    assert len(run["messages"]) == 8  # 7 personas + reconciler
    assert any(m["persona"] == "macro_catalyst" for m in run["messages"])
    assert "macro catalyst overlay -1.6" in run["calibration_notes"]


def test_catalyst_overlay_rejects_double_counted_or_unsourced_events():
    from app.features.macro.ai_regime.runner import _catalyst_overlay

    answer = {
        "vote": "OFF",
        "conviction": 100,
        "impact": 5,
        "pricing_status": "mostly_priced",
        "event_date": "2026-08-30",
        "sources": [{"title": "Source", "url": "https://example.com"}],
    }
    assert _catalyst_overlay(answer, "2026-08-30") == 0
    assert _catalyst_overlay({**answer, "pricing_status": "unpriced", "sources": []}, "2026-08-30") == 0
