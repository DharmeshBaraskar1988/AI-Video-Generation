"""SQLModel tables and session helpers. JSON payloads are stored as JSON columns."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterator

from sqlalchemy import JSON, Column
from sqlmodel import Field, Session, SQLModel, create_engine

from .config import settings


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Video(SQLModel, table=True):
    """One video job per company quarter (e.g. iqcd-q2-2026)."""
    id: str = Field(primary_key=True)
    company: str
    period: str
    status: str = "draft"  # running | review | rendering | done | failed
    thread_id: str = ""  # LangGraph thread; a new one per (re)generation
    current_node: str | None = None
    node_status: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    files: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: str | None = None
    published: bool | None = False  # finished videos start unpublished; a person publishes them
    published_at: datetime | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class Script(SQLModel, table=True):
    """Scene script (schema in CLAUDE.md), one row per video."""
    video_id: str = Field(primary_key=True, foreign_key="video.id")
    quarter: str
    status: str = "draft"  # draft | approved
    target_seconds: int = 150
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now)


class Setting(SQLModel, table=True):
    """Admin settings, key -> JSON value."""
    key: str = Field(primary_key=True)
    value: Any = Field(default=None, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=_now)


class QALog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: str | None = None
    lang: str = "en"
    question: str
    answer: str
    covered: bool = True
    top_score: float | None = None
    citations: list[Any] = Field(default_factory=list, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_now)


class StockLog(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    question: str
    ticker: str | None = None
    answer: str
    raw: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    ok: bool = True
    session_id: str | None = Field(default=None, index=True)  # stock chat conversation
    standalone: str | None = None  # question rewritten with the conversation's context
    topic_start: bool = False  # first turn of a new topic: the short-term window restarts here
    summarized: bool = False  # folded into ChatMemory.summary
    created_at: datetime = Field(default_factory=_now)


class ChatMemory(SQLModel, table=True):
    """Long-term memory of a stock chat: dense summary of turns that left the short-term window."""
    session_id: str = Field(primary_key=True)
    summary: str = ""
    turns: int = 0  # how many turns the summary covers
    updated_at: datetime = Field(default_factory=_now)


class Document(SQLModel, table=True):
    """An uploaded results document (PDF or Markdown) and what the document agent found in it."""
    id: int | None = Field(default=None, primary_key=True)
    file: str = Field(index=True, unique=True)  # stored file name in data/documents
    name: str | None = None  # original name shown to users
    company: str | None = Field(default=None, index=True)  # slug, e.g. "iqcd"
    period: str | None = Field(default=None, index=True)  # e.g. "H1 2026"
    doc_type: str | None = None  # financial_statements | press_release | investor_presentation | ...
    status: str = "uploaded"  # uploaded | classifying | indexed | extracting | review | approved | failed
    error: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))  # classification details
    pages: int = 0
    chunks: int = 0
    sha256: str = ""
    uploaded_at: datetime | None = Field(default_factory=_now)
    ingested_at: datetime | None = None


class DataReview(SQLModel, table=True):
    """Figures the agent extracted for one company and period, waiting for (or after) human approval."""
    id: str = Field(primary_key=True)  # e.g. "iqcd-h1-2026"
    company: str
    period: str
    status: str = "extracting"  # extracting | review | approved | failed
    content: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    error: str | None = None
    created_at: datetime = Field(default_factory=_now)
    updated_at: datetime = Field(default_factory=_now)


class LLMCache(SQLModel, table=True):
    """Cached LLM responses keyed by a hash of model + prompt (free tier is rate-limited)."""
    key: str = Field(primary_key=True)
    model: str
    response: str
    created_at: datetime = Field(default_factory=_now)


engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})


def init_db() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Tiny migration for the POC: add columns that are in the models but not yet in the SQLite file."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name not in existing:
                    ddl = col.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl}'))


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
