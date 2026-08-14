"""Persistencia local de trabajos de corte."""

import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def _project_base():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


DB_PATH = Path(os.getenv(
    "CORTE_DB_PATH",
    _project_base() / "data" / "corte_marmol.sqlite3",
))


def export_dir():
    """Carpeta donde la app de escritorio guarda los DXF exportados."""
    folder = _project_base() / "data" / "exportados"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with _connect() as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                payload TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)


def save_job(name, payload, job_id=None):
    now = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(payload, ensure_ascii=False)
    with _connect() as connection:
        if job_id is None:
            cursor = connection.execute(
                "INSERT INTO jobs (name, payload, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (name, encoded, now, now),
            )
            job_id = cursor.lastrowid
        else:
            connection.execute(
                "UPDATE jobs SET name = ?, payload = ?, updated_at = ? WHERE id = ?",
                (name, encoded, now, job_id),
            )
    return get_job(job_id)


def list_jobs():
    with _connect() as connection:
        rows = connection.execute(
            "SELECT id, name, created_at, updated_at FROM jobs ORDER BY updated_at DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def get_job(job_id):
    with _connect() as connection:
        row = connection.execute(
            "SELECT id, name, payload, created_at, updated_at FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        return None
    result = dict(row)
    result["payload"] = json.loads(result["payload"])
    return result
