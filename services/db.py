import json
import logging
import os
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import Json, RealDictCursor

logger = logging.getLogger(__name__)


class CallLogRepository:
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv("DATABASE_URL")
        if not self.database_url:
            logger.warning("DATABASE_URL not set. Call logs will not be persisted.")
            self.enabled = False
        else:
            self.enabled = True
            self._ensure_tables()

    def _ensure_tables(self):
        create_call_logs = """
        CREATE TABLE IF NOT EXISTS call_logs (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            call_sid VARCHAR(64) NOT NULL,
            phone_number VARCHAR(32),
            transcript TEXT,
            used_docs JSONB,
            llm_response TEXT,
            tts_url TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        create_appointments = """
        CREATE TABLE IF NOT EXISTS appointments (
            id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
            call_sid VARCHAR(64) NOT NULL,
            patient_name TEXT,
            appointment_reason TEXT,
            preferred_date TEXT,
            preferred_time TEXT,
            doctor_preference TEXT,
            metadata JSONB,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """
        with psycopg2.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
                cur.execute(create_call_logs)
                cur.execute(create_appointments)
            conn.commit()

    def insert(
        self,
        call_sid: str,
        from_number: str,
        transcript: str,
        used_docs: List[str],
        llm_response: str,
        tts_url: str,
        metadata: Dict[str, Any],
    ):
        if not self.enabled:
            logger.info("Skipping DB insert for call %s (persistence disabled)", call_sid)
            return

        insert_sql = """
        INSERT INTO call_logs (call_sid, phone_number, transcript, used_docs, llm_response, tts_url, metadata)
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb);
        """
        with psycopg2.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        call_sid,
                        from_number,
                        transcript,
                        Json(used_docs),
                        llm_response,
                        tts_url,
                        json.dumps(metadata),
                    ),
                )
            conn.commit()

    def fetch_recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        if not self.enabled:
            return []
        query = """
        SELECT call_sid, phone_number, transcript, used_docs, llm_response, tts_url, metadata, created_at
        FROM call_logs
        ORDER BY created_at DESC
        LIMIT %s;
        """
        with psycopg2.connect(self.database_url) as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (limit,))
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    def insert_appointment(
        self,
        call_sid: str,
        state: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not self.enabled:
            logger.info("Skipping appointment insert for %s (persistence disabled)", call_sid)
            return None
        insert_sql = """
        INSERT INTO appointments (
            call_sid,
            patient_name,
            appointment_reason,
            preferred_date,
            preferred_time,
            doctor_preference,
            metadata
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
        RETURNING id;
        """
        with psycopg2.connect(self.database_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    insert_sql,
                    (
                        call_sid,
                        state.get("patient_name"),
                        state.get("appointment_reason"),
                        state.get("preferred_date"),
                        state.get("preferred_time"),
                        state.get("doctor_preference"),
                        json.dumps(metadata or {}),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
        return row[0] if row else None

