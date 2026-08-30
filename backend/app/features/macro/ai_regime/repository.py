"""Persistence for AI regime runs + their message audit trail."""

from __future__ import annotations

import sqlite3

_RUN_COLS = (
    "id, created_at, trading_date, model, budget, prompt_version, "
    "score_raw, score, confidence_raw, confidence, calibration_notes, "
    "code_weighted_score, reconciler_score, weights_json, "
    "on_votes, off_votes, neutral_votes, summary, naive_score, "
    "input_snapshot_json, prompt_tokens, completion_tokens, cost_estimate_usd, status, error"
)


def get_by_date(conn: sqlite3.Connection, trading_date: str) -> dict | None:
    row = conn.execute(
        f"SELECT {_RUN_COLS} FROM ai_regime_runs WHERE trading_date = ?", (trading_date,)
    ).fetchone()
    return dict(row) if row else None


def get_latest(conn: sqlite3.Connection) -> dict | None:
    row = conn.execute(
        f"SELECT {_RUN_COLS} FROM ai_regime_runs ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return dict(row) if row else None


def history(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = conn.execute(
        "SELECT id, created_at, trading_date, model, budget, score, confidence, "
        "on_votes, off_votes, neutral_votes, naive_score, status "
        "FROM ai_regime_runs ORDER BY trading_date DESC, id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def messages(conn: sqlite3.Connection, run_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT seq, role, persona, round, prompt, completion, parsed_json, vote, "
        "conviction, prompt_tokens, completion_tokens "
        "FROM ai_regime_messages WHERE run_id = ? ORDER BY seq",
        (run_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def upsert_run(conn: sqlite3.Connection, run: dict) -> int:
    conn.execute("BEGIN")
    cur = conn.execute(
        """
        INSERT INTO ai_regime_runs
            (trading_date, model, budget, prompt_version, score_raw, score,
             confidence_raw, confidence, calibration_notes,
             code_weighted_score, reconciler_score, weights_json,
             on_votes, off_votes, neutral_votes, summary, naive_score,
             input_snapshot_json, prompt_tokens, completion_tokens,
             cost_estimate_usd, status, error)
        VALUES
            (:trading_date, :model, :budget, :prompt_version, :score_raw, :score,
             :confidence_raw, :confidence, :calibration_notes,
             :code_weighted_score, :reconciler_score, :weights_json,
             :on_votes, :off_votes, :neutral_votes, :summary, :naive_score,
             :input_snapshot_json, :prompt_tokens, :completion_tokens,
             :cost_estimate_usd, :status, :error)
        ON CONFLICT(trading_date) DO UPDATE SET
            created_at = strftime('%Y-%m-%dT%H:%M:%fZ','now'),
            model=excluded.model, budget=excluded.budget,
            prompt_version=excluded.prompt_version,
            score_raw=excluded.score_raw, score=excluded.score,
            confidence_raw=excluded.confidence_raw, confidence=excluded.confidence,
            calibration_notes=excluded.calibration_notes,
            code_weighted_score=excluded.code_weighted_score,
            reconciler_score=excluded.reconciler_score, weights_json=excluded.weights_json,
            on_votes=excluded.on_votes, off_votes=excluded.off_votes,
            neutral_votes=excluded.neutral_votes, summary=excluded.summary,
            naive_score=excluded.naive_score,
            input_snapshot_json=excluded.input_snapshot_json,
            prompt_tokens=excluded.prompt_tokens,
            completion_tokens=excluded.completion_tokens,
            cost_estimate_usd=excluded.cost_estimate_usd,
            status=excluded.status, error=excluded.error
        """,
        run,
    )
    run_id = cur.lastrowid
    if not run_id:  # ON CONFLICT path — fetch the existing id
        run_id = conn.execute(
            "SELECT id FROM ai_regime_runs WHERE trading_date = ?", (run["trading_date"],)
        ).fetchone()["id"]
    conn.execute("DELETE FROM ai_regime_messages WHERE run_id = ?", (run_id,))
    conn.execute("COMMIT")
    return int(run_id)


def insert_messages(conn: sqlite3.Connection, run_id: int, msgs: list[dict]) -> None:
    conn.execute("BEGIN")
    conn.executemany(
        """
        INSERT INTO ai_regime_messages
            (run_id, seq, role, persona, round, prompt, completion, parsed_json,
             vote, conviction, prompt_tokens, completion_tokens)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (run_id, m["seq"], m["role"], m.get("persona"), m["round"], m["prompt"],
             m["completion"], m.get("parsed_json"), m.get("vote"), m.get("conviction"),
             m.get("prompt_tokens"), m.get("completion_tokens"))
            for m in msgs
        ],
    )
    conn.execute("COMMIT")


def full(conn: sqlite3.Connection, run: dict | None) -> dict | None:
    if not run:
        return None
    return {**run, "messages": messages(conn, run["id"])}
