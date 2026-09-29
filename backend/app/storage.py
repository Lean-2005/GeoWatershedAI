"""
Lightweight persistence layer for uploaded geo-coded evidence.

The pitch deck's target stack is PostgreSQL + object storage. For a
zero-config runnable prototype we use SQLite (bundled with Python) for
metadata and the local filesystem for image bytes -- the schema and API
are written so swapping in psycopg2/S3 later only touches this file.
"""
from __future__ import annotations

import sqlite3
import time
import os
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "generated" / "geowatershed.db"
IMAGES_DIR = Path(__file__).resolve().parent.parent / "generated" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS evidence_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                lat REAL NOT NULL,
                lon REAL NOT NULL,
                captured_on TEXT,
                notes TEXT,
                valid INTEGER NOT NULL,
                validation_message TEXT,
                uploaded_at REAL NOT NULL
            )
            """
        )


def insert_image(filename, stored_path, lat, lon, captured_on, notes, valid, validation_message):
    with _conn() as conn:
        cur = conn.execute(
            """INSERT INTO evidence_images
               (filename, stored_path, lat, lon, captured_on, notes, valid, validation_message, uploaded_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (filename, stored_path, lat, lon, captured_on, notes, int(valid), validation_message, time.time()),
        )
        return cur.lastrowid


def list_images():
    with _conn() as conn:
        rows = conn.execute("SELECT * FROM evidence_images ORDER BY uploaded_at DESC").fetchall()
        return [dict(r) for r in rows]


def counts():
    with _conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS total, SUM(valid) AS valid_count FROM evidence_images"
        ).fetchone()
        total = row["total"] or 0
        valid_count = row["valid_count"] or 0
        return {"total": total, "valid": valid_count, "invalid": total - valid_count}
