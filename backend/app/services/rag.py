"""Document index: PDFs -> page-aware chunks -> multilingual-e5-small embeddings -> Chroma.

Chunks never cross pages, so every hit cites an exact {file, page, section}.
Search = cosine similarity ('query: ' prefix) blended with a keyword match boost.
The same collection later also holds video script chunks (kind="script", Step 9).
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pdfplumber
from pypdf import PdfReader
from sqlmodel import Session, select

from ..config import settings
from ..db import Document, engine

log = logging.getLogger(__name__)

COLLECTION = "dstorify"
CHUNK_TOKENS = 450  # multilingual-e5-small reads at most 512 tokens per passage
OVERLAP_LINES = 2
VECTOR_WEIGHT, KEYWORD_WEIGHT = 0.8, 0.2

_model = None
_client = None
_lock = threading.Lock()

STOPWORDS = set(
    "the and for with that this from what why how was were are has have had into its their about which when "
    "who whom than then there these those over under after before during between per not but all any".split()
)
NOTE_HEADING = re.compile(r"^(\d{1,2})\.\s+([A-Z][A-Za-z0-9 ,'&()/-]{3,80})$")
SKIP_HEADING = re.compile(
    r"^(industries qatar|page \d+|\d+|qr\s*'?000|as at|for the|condensed consolidated interim financial information$)",
    re.I,
)


# ---------- model + store ----------

def model():
    global _model
    with _lock:
        if _model is None:
            from sentence_transformers import SentenceTransformer

            _model = SentenceTransformer(settings.embedding_model)
    return _model


def collection():
    global _client
    with _lock:
        if _client is None:
            import chromadb

            settings.chroma_dir.mkdir(parents=True, exist_ok=True)
            _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})


def embed(texts: list[str], kind: str) -> list[list[float]]:
    """kind: 'passage' for stored chunks, 'query' for searches (e5 convention)."""
    vectors = model().encode([f"{kind}: {t}" for t in texts], normalize_embeddings=True, batch_size=16)
    return vectors.tolist()


def token_count(text: str) -> int:
    return len(model().tokenizer.tokenize(text))


# ---------- PDF reading ----------

def clean(text: str) -> str:
    text = text.replace("�", "'").replace(" ", " ")
    return re.sub(r"[ \t]+", " ", text)


def page_heading(lines: list[str]) -> str | None:
    """Slide/page title: the first short line with words that is not a running header."""
    for line in lines[:8]:
        s = line.strip()
        if 4 <= len(s) <= 90 and re.search(r"[A-Za-z]{3}", s) and not SKIP_HEADING.match(s) and "IR Presentation" not in s:
            return s
    return None


def table_markdown(table: list[list[str | None]]) -> str | None:
    """Keep real tables only: 3+ rows, 2+ columns and some numeric cells."""
    rows = [[clean(c or "").strip().replace("\n", " ") for c in row] for row in table if row]
    rows = [r for r in rows if any(r)]
    if len(rows) < 3 or max(len(r) for r in rows) < 2:
        return None
    numeric = sum(bool(re.search(r"\d", c)) for r in rows for c in r)
    if numeric < 4:
        return None
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + " --- |" * width]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def read_pdf(path: Path) -> list[dict[str, Any]]:
    """[{page, text, tables[], heading}] with 1-based page numbers."""
    reader = PdfReader(str(path))
    pages = []
    with pdfplumber.open(str(path)) as plumber:
        for i, page in enumerate(reader.pages):
            text = clean(page.extract_text() or "")
            try:
                tables = [md for t in plumber.pages[i].extract_tables() if (md := table_markdown(t))]
            except Exception:  # noqa: BLE001 - a bad table should not stop ingestion
                tables = []
            lines = [l for l in text.splitlines() if l.strip()]
            pages.append({"page": i + 1, "text": text, "lines": lines, "tables": tables, "heading": page_heading(lines)})
    return pages


# ---------- chunking ----------

def chunk_pages(file: str, pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    section = None
    for p in pages:
        section = p["heading"] or section
        buf: list[str] = []
        buf_tokens = 0
        current = section

        def flush() -> None:
            text = "\n".join(buf).strip()
            if len(text) > 40:
                chunks.append({"file": file, "page": p["page"], "section": current or "", "type": "text", "text": text})

        for line in p["lines"]:
            m = NOTE_HEADING.match(line.strip())
            if m:  # a numbered note starts a new section
                if buf:
                    flush()
                    buf, buf_tokens = [], 0
                current = section = f"{m.group(1)}. {m.group(2)}"
            n = token_count(line)
            if buf and buf_tokens + n > CHUNK_TOKENS:
                flush()
                buf = buf[-OVERLAP_LINES:]
                buf_tokens = sum(token_count(x) for x in buf)
            buf.append(line)
            buf_tokens += n
        if buf:
            flush()
        for t in p["tables"]:
            chunks.append({"file": file, "page": p["page"], "section": current or "", "type": "table", "text": t[:4000]})
    return chunks


# ---------- ingest ----------

SUPPORTED_SUFFIXES = (".pdf", ".md", ".markdown")
MD_HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*#*\s*$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_markdown(path: Path) -> list[dict[str, Any]]:
    """Markdown as 'pages': one per top-level section, so citations read [file §N] with the heading."""
    text = clean(path.read_text(encoding="utf-8", errors="replace"))
    sections: list[dict[str, Any]] = []
    heading, buf = None, []
    for line in text.splitlines():
        m = MD_HEADING.match(line.strip())
        if m and len(m.group(1)) <= 2 and buf:
            sections.append({"heading": heading, "lines": buf})
            buf = []
        if m:
            heading = m.group(2).strip()
        if line.strip():
            buf.append(line.rstrip())
    if buf:
        sections.append({"heading": heading, "lines": buf})
    return [
        {"page": i + 1, "text": "\n".join(sec["lines"]), "lines": sec["lines"], "tables": [], "heading": sec["heading"]}
        for i, sec in enumerate(sections)
    ]


def read_document(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in (".md", ".markdown"):
        return read_markdown(path)
    raise ValueError(f"Unsupported document type: {path.name} (use PDF or Markdown)")


def first_pages_text(path: Path, max_chars: int = 7000) -> str:
    """Opening text of a document, for classification (company, period, type)."""
    out, total = [], 0
    for p in read_document(path):
        t = p["text"].strip()
        if not t:
            continue
        out.append(f"[page {p['page']}]\n{t}")
        total += len(t)
        if total >= max_chars:
            break
    return "\n\n".join(out)[:max_chars]


def doc_path(doc: Document) -> Path:
    return settings.documents_dir / doc.file


def index_document(doc_id: int) -> dict[str, Any]:
    """(Re)index one document. Every chunk carries the document's company, period and year."""
    col = collection()
    with Session(engine) as s:
        doc = s.get(Document, doc_id)
        path = doc_path(doc)
        pages = read_document(path)
        display = doc.name or doc.file
        chunks = chunk_pages(display, pages)
        col.delete(where={"doc_id": doc_id})
        year = int(doc.period.split()[1]) if doc.period else 0
        if chunks:
            col.add(
                ids=[f"doc:{doc_id}:{c['page']}:{i}" for i, c in enumerate(chunks)],
                documents=[c["text"] for c in chunks],
                embeddings=embed([c["text"] for c in chunks], "passage"),
                metadatas=[
                    {"kind": "document", "doc_id": doc_id, "file": display, "path": doc.file, "page": c["page"],
                     "section": c["section"], "type": c["type"], "company": doc.company or "",
                     "period": doc.period or "", "year": year, "doc_type": doc.doc_type or ""}
                    for c in chunks
                ],
            )
        doc.pages, doc.chunks, doc.sha256 = len(pages), len(chunks), _sha256(path)
        doc.ingested_at = datetime.now(timezone.utc)
        s.add(doc)
        s.commit()
        empty = [p["page"] for p in pages if len(p["text"].strip()) < 40]
    return {"doc_id": doc_id, "pages": len(pages), "chunks": len(chunks), "pages_without_text": empty}


def unindex_document(doc_id: int) -> None:
    collection().delete(where={"doc_id": doc_id})


def register_folder_files() -> list[int]:
    """Documents dropped straight into data/documents get a database row (status 'uploaded')."""
    new_ids = []
    with Session(engine) as s:
        known = {d.file for d in s.exec(select(Document)).all()}
        for path in sorted(settings.documents_dir.iterdir()):
            if (path.suffix.lower() in SUPPORTED_SUFFIXES and path.name not in known
                    and not path.name.lower().startswith("readme")):
                doc = Document(file=path.name, name=path.name, status="uploaded")
                s.add(doc)
                s.commit()
                new_ids.append(doc.id)
    return new_ids


def list_documents() -> list[dict[str, Any]]:
    with Session(engine) as s:
        docs = s.exec(select(Document).order_by(Document.uploaded_at.desc())).all()
    out = []
    for d in docs:
        path = settings.documents_dir / d.file
        if not path.exists():
            continue
        out.append({
            "id": d.id,
            "file": d.file,
            "name": d.name or d.file,
            "company": d.company,
            "period": d.period,
            "doc_type": d.doc_type,
            "status": d.status or "uploaded",
            "error": d.error,
            "meta": d.meta or {},
            "size_kb": round(path.stat().st_size / 1024),
            "indexed": bool(d.ingested_at) and d.chunks > 0,
            "pages": d.pages or None,
            "chunks": d.chunks or None,
            "uploaded_at": d.uploaded_at,
            "ingested_at": d.ingested_at,
            "stale": bool(d.sha256) and d.sha256 != _sha256(path),
        })
    return out


def doc_where(company: str | None = None, period: str | None = None, year: int | None = None) -> dict[str, Any]:
    """Chroma filter for document chunks of one company (and optionally one period or year)."""
    conds: list[dict[str, Any]] = [{"kind": "document"}]
    if company:
        conds.append({"company": company})
    if period:
        conds.append({"period": period})
    if year:
        conds.append({"year": year})
    return conds[0] if len(conds) == 1 else {"$and": conds}


# ---------- search ----------

def _terms(text: str) -> set[str]:
    words = re.findall(r"[A-Za-z؀-ۿ]{3,}|\d[\d.,]*", text.lower())
    return {w.strip(".,") for w in words if w not in STOPWORDS}


def search(query: str, k: int = 8, where: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Top-k chunks: 0.8 * cosine similarity + 0.2 * share of query terms found in the chunk."""
    col = collection()
    if col.count() == 0:
        return []
    res = col.query(
        query_embeddings=embed([query], "query"),
        n_results=min(max(k * 3, 20), col.count()),
        where=where or {"kind": "document"},
    )
    terms = _terms(query)
    hits = []
    for cid, text, meta, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
        sim = 1.0 - dist
        kw = len(terms & _terms(text)) / len(terms) if terms else 0.0
        hits.append({"id": cid, "text": text, **meta, "sim": round(sim, 4), "kw": round(kw, 3),
                     "score": round(VECTOR_WEIGHT * sim + KEYWORD_WEIGHT * kw, 4)})
    hits.sort(key=lambda h: -h["score"])
    return hits[:k]


def get_chunks(ids: list[str]) -> list[dict[str, Any]]:
    if not ids:
        return []
    res = collection().get(ids=ids)
    return [{"id": i, "text": t, **m} for i, t, m in zip(res["ids"], res["documents"], res["metadatas"])]


# ---------- video scripts (Step 9) ----------

def index_script(video_id: str, lang: str, scenes: list[dict[str, Any]]) -> int:
    """Index each narrated scene with its start time so Q&A answers can jump to it.
    `scenes` are the narration timing entries: {id, type, start, end, text}."""
    col = collection()
    col.delete(where={"$and": [{"kind": "script"}, {"video_id": video_id}, {"lang": lang}]})
    scenes = [s for s in scenes if s.get("text", "").strip()]
    if not scenes:
        return 0
    col.add(
        ids=[f"script:{video_id}:{lang}:{s['id']}" for s in scenes],
        documents=[s["text"] for s in scenes],
        embeddings=embed([s["text"] for s in scenes], "passage"),
        metadatas=[
            {"kind": "script", "video_id": video_id, "lang": lang, "scene": s["id"], "scene_type": s["type"],
             "start": float(s["start"]), "end": float(s["end"]), "file": "", "page": 0, "section": s["type"], "type": "script"}
            for s in scenes
        ],
    )
    return len(scenes)
