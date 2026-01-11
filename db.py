from __future__ import annotations

import os
import json
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
import psycopg2.extras
import streamlit as st
from streamlit.runtime.secrets import Secrets, StreamlitSecretNotFoundError


def _build_url_from_parts(source: Dict[str, Any]) -> str:
    user = source.get("user") or source.get("DB_USER")
    password = source.get("password") or source.get("DB_PASSWORD")
    host = source.get("host") or source.get("DB_HOST")
    port = source.get("port") or source.get("DB_PORT")
    dbname = source.get("dbname") or source.get("DB_NAME") or source.get("database")
    if not all([user, password, host, port, dbname]):
        return ""
    user = str(user).strip()
    password = urllib.parse.quote_plus(str(password).strip())
    host = str(host).strip()
    port = str(port).strip()
    dbname = str(dbname).strip()
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"


def _get_db_url() -> str:
    # Prefer secrets-derived pooler settings first
    try:
        secrets: Optional[Secrets] = st.secrets
        if secrets:
            alt = _build_url_from_parts(secrets)
            if alt:
                return alt
            url = secrets.get("DATABASE_URL")
            if url:
                return url
    except StreamlitSecretNotFoundError:
        pass

    # Next, try env parts (DB_USER/DB_PASSWORD or user/password, etc.)
    env_parts = {
        "user": os.getenv("user") or os.getenv("DB_USER"),
        "password": os.getenv("password") or os.getenv("DB_PASSWORD"),
        "host": os.getenv("host") or os.getenv("DB_HOST"),
        "port": os.getenv("port") or os.getenv("DB_PORT"),
        "dbname": os.getenv("dbname") or os.getenv("DB_NAME") or os.getenv("database"),
    }
    alt_env = _build_url_from_parts(env_parts)
    if alt_env:
        return alt_env

    # Last resort: DATABASE_URL
    env_url = os.getenv("DATABASE_URL")
    return env_url or ""


def connect():
    url = _get_db_url()
    if not url:
        raise RuntimeError("DATABASE_URL not configured in secrets or environment.")
    return psycopg2.connect(url, cursor_factory=psycopg2.extras.DictCursor)


def init_db() -> None:
    """
    Create tables if they do not exist.
    """
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        create table if not exists runs (
            id bigserial primary key,
            topic text,
            model text,
            search_mode text,
            time_window text,
            output_style text,
            summary text,
            raw_json jsonb,
            created_at timestamptz default now()
        );
        """
    )
    # Backfill columns if the table existed before.
    cur.execute("alter table runs add column if not exists summary text;")
    cur.execute("alter table runs add column if not exists raw_json jsonb;")
    cur.execute(
        """
        create table if not exists messages (
            id bigserial primary key,
            run_id bigint references runs(id) on delete cascade,
            role text,
            content text,
            created_at timestamptz default now()
        );
        """
    )
    cur.execute(
        """
        create table if not exists run_items (
            id bigserial primary key,
            run_id bigint references runs(id) on delete cascade,
            topic text,
            source_title text,
            url text,
            source_type text,
            key_takeaway text,
            video_angle text,
            credibility_score numeric,
            notes text,
            citations text[],
            created_at timestamptz default now()
        );
        """
    )
    conn.commit()
    cur.close()
    conn.close()


def save_run(
    topic: str,
    model: str,
    search_mode: str,
    time_window: str,
    output_style: str,
    messages: List[Dict[str, str]],
    summary: Optional[str],
    raw_json: Optional[Dict[str, Any]],
    items: Optional[List[Dict[str, Any]]],
) -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        """
        insert into runs (topic, model, search_mode, time_window, output_style, summary, raw_json)
        values (%s, %s, %s, %s, %s, %s, %s)
        returning id;
        """,
        (topic, model, search_mode, time_window, output_style, summary, json.dumps(raw_json) if raw_json else None),
    )
    run_id = cur.fetchone()[0]

    rows = [(run_id, m.get("role"), m.get("content")) for m in messages if m.get("role") and m.get("content")]
    if rows:
        psycopg2.extras.execute_values(
            cur,
            "insert into messages (run_id, role, content) values %s",
            rows,
        )

    item_rows = []
    if items:
        for it in items:
            item_rows.append(
                (
                    run_id,
                    it.get("topic"),
                    it.get("source_title"),
                    it.get("url"),
                    it.get("source_type"),
                    it.get("key_takeaway"),
                    it.get("video_angle"),
                    it.get("credibility_score"),
                    it.get("notes"),
                    it.get("citations"),
                )
            )
    if item_rows:
        psycopg2.extras.execute_values(
            cur,
            """
            insert into run_items (
                run_id, topic, source_title, url, source_type, key_takeaway,
                video_angle, credibility_score, notes, citations
            ) values %s
            """,
            item_rows,
        )

    conn.commit()
    cur.close()
    conn.close()
    return run_id


def fetch_latest_run() -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select id, topic, model, search_mode, time_window, output_style, summary, raw_json, created_at from runs order by created_at desc limit 1;"
    )
    run_row = cur.fetchone()
    if not run_row:
        cur.close()
        conn.close()
        return None, [], []

    run = dict(run_row)
    cur.execute(
        "select role, content, created_at from messages where run_id = %s order by created_at asc;",
        (run["id"],),
    )
    messages = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """
        select topic, source_title, url, source_type, key_takeaway, video_angle,
               credibility_score, notes, citations, created_at
        from run_items where run_id = %s order by created_at asc;
        """,
        (run["id"],),
    )
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return run, messages, items


def fetch_runs(limit: int = 20) -> List[Dict[str, Any]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select id, topic, model, search_mode, time_window, output_style, summary, created_at from runs order by created_at desc limit %s;",
        (limit,),
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return rows


def fetch_run_with_messages(run_id: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    conn = connect()
    cur = conn.cursor()
    cur.execute(
        "select id, topic, model, search_mode, time_window, output_style, summary, raw_json, created_at from runs where id = %s;",
        (run_id,),
    )
    run_row = cur.fetchone()
    if not run_row:
        cur.close()
        conn.close()
        return None, [], []
    run = dict(run_row)
    cur.execute(
        "select role, content, created_at from messages where run_id = %s order by created_at asc;",
        (run_id,),
    )
    messages = [dict(r) for r in cur.fetchall()]
    cur.execute(
        """
        select topic, source_title, url, source_type, key_takeaway, video_angle,
               credibility_score, notes, citations, created_at
        from run_items where run_id = %s order by created_at asc;
        """,
        (run_id,),
    )
    items = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return run, messages, items


def delete_run(run_id: int) -> None:
    conn = connect()
    cur = conn.cursor()
    cur.execute("delete from runs where id = %s;", (run_id,))
    conn.commit()
    cur.close()
    conn.close()
