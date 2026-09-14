import re
import time
import uuid
from contextlib import contextmanager
from typing import Optional, List, Dict, Any

import psycopg
from psycopg.rows import dict_row
from pgvector.psycopg import register_vector
from chromadb.utils import embedding_functions

from src.config import settings
from src.schemas import LessonKnowledgeDoc

EMBED_DIM = 384  # all-MiniLM-L6-v2 (chromadb's default embedding function)
_embedder = embedding_functions.DefaultEmbeddingFunction()


def _embed(texts: List[str]) -> List[List[float]]:
    return list(_embedder(texts))


@contextmanager
def _conn():
    conn = psycopg.connect(settings.DATABASE_URL, autocommit=True, row_factory=dict_row)
    try:
        register_vector(conn)
        yield conn
    finally:
        conn.close()


def _init_db():
    # The vector extension must exist before register_vector() can look up its
    # type OID, so this first connection is opened without it.
    with psycopg.connect(settings.DATABASE_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")

    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS lesson_chunks (
                    id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    video_title TEXT,
                    video_url TEXT,
                    timestamp TEXT,
                    deep_link TEXT,
                    topic TEXT,
                    cohort_tag TEXT,
                    content TEXT NOT NULL,
                    embedding vector({EMBED_DIM})
                )
            """)
            cur.execute(f"""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    sender TEXT,
                    group_id TEXT,
                    cohort_tag TEXT,
                    category TEXT,
                    deadline TEXT,
                    summary TEXT,
                    date TEXT,
                    timestamp_ms BIGINT,
                    content TEXT NOT NULL,
                    embedding vector({EMBED_DIM})
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_lesson_cohort ON lesson_chunks (cohort_tag)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_cohort ON chat_messages (cohort_tag)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_chat_timestamp_ms ON chat_messages (timestamp_ms)")


if settings.DATABASE_URL:
    _init_db()
else:
    print("Warning: DATABASE_URL is not set. Please add your Neon/Postgres connection string to .env.")


def lesson_count() -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM lesson_chunks")
            return cur.fetchone()["c"]


def chat_count() -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM chat_messages")
            return cur.fetchone()["c"]


def get_all_lesson_video_urls() -> set:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT video_url FROM lesson_chunks WHERE video_url IS NOT NULL")
            return {row["video_url"] for row in cur.fetchall()}


def get_all_chat_messages() -> List[Dict[str, Any]]:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT content, cohort_tag FROM chat_messages")
            return cur.fetchall()


def add_raw_chunks_to_kb(chunks: List[Dict[str, Any]]):
    """Low-level insert for lesson_chunks. Each dict needs: id, video_id,
    video_title, video_url, timestamp, deep_link, topic, cohort_tag, content."""
    if not chunks:
        return
    embeddings = _embed([c["content"] for c in chunks])
    with _conn() as conn:
        with conn.cursor() as cur:
            for chunk, embedding in zip(chunks, embeddings):
                cur.execute("""
                    INSERT INTO lesson_chunks
                        (id, video_id, video_title, video_url, timestamp, deep_link, topic, cohort_tag, content, embedding)
                    VALUES
                        (%(id)s, %(video_id)s, %(video_title)s, %(video_url)s, %(timestamp)s, %(deep_link)s, %(topic)s, %(cohort_tag)s, %(content)s, %(embedding)s)
                    ON CONFLICT (id) DO UPDATE SET
                        video_title = EXCLUDED.video_title,
                        video_url = EXCLUDED.video_url,
                        timestamp = EXCLUDED.timestamp,
                        deep_link = EXCLUDED.deep_link,
                        topic = EXCLUDED.topic,
                        cohort_tag = EXCLUDED.cohort_tag,
                        content = EXCLUDED.content,
                        embedding = EXCLUDED.embedding
                """, {**chunk, "embedding": embedding})


def add_lesson_to_kb(lesson: LessonKnowledgeDoc, cohort_tag: str = "Cohort 1"):
    cohort_slug = re.sub(r'\W+', '_', cohort_tag.strip().lower()).strip('_')
    chunks = []
    for idx, chunk in enumerate(lesson.chunks):
        doc_id = f"{cohort_slug}_{lesson.video_id}_chunk_{idx}"
        deep_link = f"{lesson.video_url}&t={chunk.start_seconds}s"
        content = f"[{cohort_tag}] Topic: {chunk.topic}\nTimestamp: {chunk.timestamp_str}\nSummary: {chunk.summary}\nTakeaways: {', '.join(chunk.key_takeaways)}"
        chunks.append({
            "id": doc_id,
            "video_id": lesson.video_id,
            "video_title": lesson.video_title,
            "video_url": lesson.video_url,
            "timestamp": chunk.timestamp_str,
            "deep_link": deep_link,
            "topic": chunk.topic,
            "cohort_tag": cohort_tag,
            "content": content,
        })
    add_raw_chunks_to_kb(chunks)


def get_all_ingested_lessons() -> List[Dict[str, Any]]:
    """Returns all parsed video lessons grouped by (video_id, cohort_tag)."""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT video_id, video_title, cohort_tag, topic, timestamp, deep_link, content
                FROM lesson_chunks
                ORDER BY video_id, cohort_tag
            """)
            rows = cur.fetchall()

    lessons: Dict[Any, Dict[str, Any]] = {}
    for row in rows:
        key = (row["video_id"], row["cohort_tag"])
        if key not in lessons:
            lessons[key] = {
                "video_id": row["video_id"],
                "video_title": row["video_title"] or "Video Lesson",
                "cohort_tag": row["cohort_tag"] or "Cohort 1",
                "chunks": []
            }
        lessons[key]["chunks"].append({
            "topic": row["topic"] or "Topic",
            "timestamp": row["timestamp"] or "00:00",
            "deep_link": row["deep_link"] or "",
            "content": row["content"]
        })
    return list(lessons.values())


def query_kb(query_text: str, cohort_tag: Optional[str] = None, n_results: int = 4) -> str:
    embedding = _embed([query_text])[0]
    with _conn() as conn:
        with conn.cursor() as cur:
            if cohort_tag:
                cur.execute("""
                    SELECT content, cohort_tag, topic, timestamp, deep_link
                    FROM lesson_chunks
                    WHERE cohort_tag = %s
                    ORDER BY embedding <=> %s
                    LIMIT %s
                """, (cohort_tag, embedding, n_results))
            else:
                cur.execute("""
                    SELECT content, cohort_tag, topic, timestamp, deep_link
                    FROM lesson_chunks
                    ORDER BY embedding <=> %s
                    LIMIT %s
                """, (embedding, n_results))
            rows = cur.fetchall()

    if not rows:
        return "No specific lesson context found."

    context_chunks = [
        f"[{row['cohort_tag'] or 'Cohort'} | {row['topic'] or 'Lesson'} at {row['timestamp'] or ''}] (Link: {row['deep_link'] or ''}):\n{row['content']}"
        for row in rows
    ]
    return "\n\n".join(context_chunks)


def add_chat_message_to_archive(sender: str, message: str, group_id: str, cohort_tag: str = "Cohort 1", category: str = "GENERAL", summary: str = "", deadline: str = ""):
    ts_ms = int(time.time() * 1000)
    doc_id = f"live_{ts_ms}_{uuid.uuid4().hex[:8]}"
    content = f"[{cohort_tag}] From {sender} ({category}): {message}"
    if summary:
        content += f"\nSummary: {summary}"
    if deadline:
        content += f"\nDeadline: {deadline}"

    embedding = _embed([content])[0]
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_messages
                    (id, sender, group_id, cohort_tag, category, deadline, summary, timestamp_ms, content, embedding)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (doc_id, sender, group_id, cohort_tag, category, deadline or "", summary or "", ts_ms, content, embedding))


def query_chat_archive(query_text: str, cohort_tag: Optional[str] = None, n_results: int = 8) -> str:
    embedding = _embed([query_text])[0]
    with _conn() as conn:
        with conn.cursor() as cur:
            if cohort_tag:
                cur.execute("""
                    SELECT content, cohort_tag
                    FROM chat_messages
                    WHERE cohort_tag = %s
                    ORDER BY embedding <=> %s
                    LIMIT %s
                """, (cohort_tag, embedding, n_results))
            else:
                cur.execute("""
                    SELECT content, cohort_tag
                    FROM chat_messages
                    ORDER BY embedding <=> %s
                    LIMIT %s
                """, (embedding, n_results))
            rows = cur.fetchall()

    if not rows:
        return "No past chat messages found matching this query."

    return "\n\n".join(f"• [{row['cohort_tag'] or 'Cohort'}] {row['content']}" for row in rows)


def get_recent_catchup_context(cohort_tag: Optional[str] = None, n_results: int = 30) -> str:
    with _conn() as conn:
        with conn.cursor() as cur:
            if cohort_tag:
                cur.execute("""
                    SELECT content FROM chat_messages
                    WHERE cohort_tag = %s AND category != 'HISTORICAL_CHAT'
                    ORDER BY timestamp_ms DESC
                    LIMIT %s
                """, (cohort_tag, n_results))
            else:
                cur.execute("""
                    SELECT content FROM chat_messages
                    WHERE category != 'HISTORICAL_CHAT'
                    ORDER BY timestamp_ms DESC
                    LIMIT %s
                """, (n_results,))
            rows = cur.fetchall()

    if not rows:
        return "No recent live activity recorded yet for this cohort."

    # Reverse back to chronological order (oldest first among the recent batch)
    docs = [row["content"] for row in reversed(rows)]
    return "\n\n".join(docs)


def ingest_whatsapp_chat_export_text(raw_text: str, cohort_tag: str = "Cohort 1", group_id: str = "cohort_history") -> int:
    pattern = r'(?:\[?(\d{1,2}[\/\.-]\d{1,2}[\/\.-]\d{2,4}),?\s+(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[APap][Mm])?)\]?)\s*(?:- )?([^:]+):\s*(.+)'

    entries = []
    for match in re.finditer(pattern, raw_text):
        date, msg_time, sender, message = match.groups()
        message_clean = message.strip()
        sender_clean = sender.strip()

        if "<Media omitted>" in message_clean or "Messages and calls are end-to-end encrypted" in message_clean:
            continue

        content = f"[{cohort_tag}] Date: {date} {msg_time} | Sender: {sender_clean}\nMessage: {message_clean}"
        entries.append({
            "id": str(uuid.uuid4()),
            "sender": sender_clean,
            "group_id": group_id,
            "cohort_tag": cohort_tag,
            "category": "HISTORICAL_CHAT",
            "date": date,
            "content": content,
        })

    if not entries:
        return 0

    with _conn() as conn:
        with conn.cursor() as cur:
            for i in range(0, len(entries), 50):
                batch = entries[i:i + 50]
                embeddings = _embed([e["content"] for e in batch])
                ts_ms = int(time.time() * 1000)
                for entry, embedding in zip(batch, embeddings):
                    cur.execute("""
                        INSERT INTO chat_messages
                            (id, sender, group_id, cohort_tag, category, date, timestamp_ms, content, embedding)
                        VALUES
                            (%(id)s, %(sender)s, %(group_id)s, %(cohort_tag)s, %(category)s, %(date)s, %(timestamp_ms)s, %(content)s, %(embedding)s)
                    """, {**entry, "timestamp_ms": ts_ms, "embedding": embedding})

    return len(entries)
