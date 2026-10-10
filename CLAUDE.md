# D-Storify Quarterly Results POC

Two-day proof of concept. Turn a company's quarterly results into:

1. **Results video** - one click, 2-3 minutes, branded, English + Arabic, editable script.
2. **Document summary** - RAG over results PDFs, cited executive summary (EN + AR).
3. **Video Q&A** - ask questions beside the player; answers cite the script/documents and jump to a timestamp.
4. **Stock chatbot** - natural-language questions about QSE stocks; precise prices from a live source.
5. **Admin settings** - voices per language, music, video length, model, review switch, NotebookLM video import.

Build it one step at a time from `docs/BUILD_STEPS.md`. Finish and verify a step before starting the next.
The interactive architecture is in `docs/architecture.html` (open in a browser).

## Golden rules

- **Numbers never come from the language model.** Scripts use placeholders like `{{revenue}}`; `factcheck.py` fills them from the quarter data file and rejects any digit the LLM typed itself. Stock prices come only from the price tool; changes are computed in Python.
- **Uploaded documents are the data source.** Users upload results PDFs/Markdown on the Documents page; the document agent (`services/doc_agent.py`) classifies them (company, period), indexes them with company/period metadata, and extracts headline figures **copied with an exact quote**. Python checks each number is printed in the cited passage and converts units; nothing reaches a quarter file until a person approves the data review. The LLM never supplies a figure from its own knowledge.
- **Every generated fact is traceable.** Summary and Q&A answers carry citations (file + page, or video timestamp). Stock answers show source, timestamp and a delayed/closed flag.
- **Demo data is labelled.** `data/quarters/iqcd_2026.json` is Industries Qatar's published data used as sample input. The UI shows a "Demo data" badge when `_note` contains DEMO.
- **Free stack only** for the POC (see Stack). Keep providers behind small interfaces so paid options plug in later.
- **Gemini free tier is rate-limited (~10 requests/min).** Make one LLM call per job stage (whole scene list at once), cache results in SQLite, and retry with backoff (`tenacity`). Never call the LLM in a loop per sentence.
- Arabic is first-class: right-to-left layout in UI and video scenes, Arabic fonts, Arabic voice. Use Western digits in Arabic scenes unless the admin setting says otherwise.
- Windows is the dev machine. Use `pathlib`, avoid shell-specific commands in Python, call FFmpeg/Node via `subprocess` with argument lists.

## Stack (free)

| Layer | Choice |
| --- | --- |
| Back end | Python 3.12, FastAPI, SQLModel + SQLite, background tasks |
| Orchestration | LangGraph (video graph with human-review interrupt, Q&A graph, stock agent) |
| Language model | Gemini free tier via `google-genai`; model name from `GEMINI_MODEL` in `.env` |
| Embeddings | `sentence-transformers`, `intfloat/multilingual-e5-small` (prefix `query: ` / `passage: `) |
| Vector store | ChromaDB, persistent at `CHROMA_DIR` |
| PDF reading | `pypdf` for text, `pdfplumber` for tables, page numbers kept |
| Voice | `edge-tts` (free neural voices). EN: `en-US-GuyNeural` / `en-GB-SoniaNeural`. AR: `ar-QA-MoazNeural` / `ar-QA-AmalNeural`. Use `Communicate(..., boundary="WordBoundary")` to get per-word timings (edge-tts 7 defaults to sentence boundaries) |
| Video | Remotion (React/TypeScript) in `video/`, rendered with `npx remotion render`; FFmpeg mixes music under voice |
| Front end | Next.js (App Router, TypeScript) + Tailwind + shadcn/ui in `frontend/` |
| Stock data | `yfinance` (QSE tickers end in `.QA`, e.g. `IQCD.QA`, `QNBK.QA`), optional oanor API; 60 s cache |
| News | `ddgs` (DuckDuckGo search, no key) - for context only, never prices |

Later paid options (do not build now, keep the interface): Claude/OpenAI LLMs, ElevenLabs or OpenAI TTS, HeyGen avatar, licensed QSE feed, pgvector.

## Folder structure

```
dstorify-poc/
├── CLAUDE.md                 # this file
├── .env.example / .env       # settings (install.bat creates .env)
├── setup/                    # check_system.bat, install.bat, pick_gemini_model.py, voice tests
├── docs/                     # BUILD_STEPS.md, architecture.html
├── data/
│   ├── quarters/             # iqcd_2026.json (demo quarter data)
│   ├── documents/            # results PDFs for RAG
│   ├── brand/                # logo.svg, brand.json
│   └── music/                # royalty-free tracks + LICENSES.txt
├── backend/
│   ├── requirements.txt
│   └── app/
│       ├── main.py           # FastAPI app, CORS for FRONTEND_URL, /outputs static mount
│       ├── config.py         # loads .env
│       ├── db.py             # SQLModel tables: Video, Script, Setting, QALog, StockLog, Document
│       ├── api/              # quarters.py, scripts.py, videos.py, documents.py, qa.py, stock.py, settings.py
│       ├── graphs/           # video_graph.py, qa_graph.py, stock_agent.py
│       ├── services/
│       │   ├── llm.py        # Gemini wrapper: rate limit, retry, JSON mode, cache
│       │   ├── quarters.py   # load/validate quarter files, derive missing quarters
│       │   ├── factcheck.py  # fill placeholders, detect stray numbers
│       │   ├── rag.py        # ingest PDFs, chunk, embed, search
│       │   ├── tts/          # base.py (interface), edge.py, silma.py (stub)
│       │   ├── render.py     # write props JSON, run Remotion, FFmpeg mix
│       │   └── stock.py      # tickers, quotes, history, cache
│       ├── prompts/          # script.md, translate_ar.md, summary_disclosure.md, summary_translate_ar.md, qa.md, stock.md
│       └── store/            # dstorify.db, chroma/ (git-ignored)
├── video/                    # Remotion project
│   └── src/
│       ├── Root.tsx          # registers QuarterlyVideo composition
│       ├── QuarterlyVideo.tsx
│       ├── scenes/           # Intro, KpiCards, TrendChart, Drivers, Segments, Outlook, Outro
│       ├── components/       # Captions, CountUp, Logo, ChangeArrow
│       └── theme/            # brand.ts (reads brand.json), rtl.ts, fonts.ts
├── frontend/                 # Next.js app
│   ├── app/                  # / (dashboard), /scripts/[id], /videos/[id], /summary, /chat, /admin
│   └── components/           # ScriptEditor, ScenePreview, VideoPlayer, QAPanel, StockChat, VoicePicker
└── outputs/                  # audio/, videos/, scripts/, voice_test/ (git-ignored)
```

## Data contracts

### Quarter file (`data/quarters/*.json`)
Use the existing `iqcd_2026.json` shape: `company`, `current_quarter`, `quarters[]` (period, months, revenue, net_profit, eps_qr, derived, sources), `history_net_profit[]`, `narrative_drivers[]`, `source_documents{}`. Units: QR million. A `derived: true` quarter must show a small "derived" note in UI and never be called "reported".

### Script (`outputs/scripts/{video_id}.json`, also in SQLite)
```json
{
  "video_id": "iqcd-q2-2026",
  "quarter": "Q2 2026",
  "status": "draft | approved",
  "target_seconds": 150,
  "scenes": [
    {
      "id": "s1",
      "type": "intro | kpis | trend | drivers | segments | outlook | outro",
      "en": "In the second quarter of 2026, revenue reached {{revenue}} ...",
      "ar": "...",
      "data_keys": ["revenue", "net_profit"],
      "visual": { "chart": "bar", "series": ["revenue"], "highlight": "net_profit" }
    }
  ],
  "placeholders": { "revenue": { "value": 1734, "display_en": "QR 1.7 billion", "display_ar": "1.7 مليار ريال قطري", "derived": true } },
  "checks": { "numbers_total": 14, "numbers_ok": 14, "stray_numbers": [] }
}
```
Placeholder display strings are formatted in Python (`factcheck.format_qr`), never by the LLM. Losses read as "a net loss of QR 518 million", not "-518".

### Video props (`outputs/videos/{video_id}_{lang}.props.json` -> Remotion)
```json
{
  "language": "ar",
  "direction": "rtl",
  "brand": { "...": "from data/brand/brand.json" },
  "audio": "outputs/audio/iqcd-q2-2026_ar.mp3",
  "durationSeconds": 152.4,
  "scenes": [ { "id": "s1", "type": "intro", "start": 0.0, "end": 9.8, "text": "...", "data": {} } ],
  "words": [ { "text": "...", "start": 0.12, "end": 0.48 } ],
  "demo": true
}
```
Scene `start`/`end` come from word timings (first/last word of that scene's text). Remotion `durationInFrames = ceil(durationSeconds * 30)`.

## Pipelines

**Video graph (LangGraph):** `load_quarter -> gather_context (narrative_drivers; Chroma once Step 8 exists) -> draft_script (Gemini, JSON scene list with placeholders) -> factcheck -> translate_ar (Gemini, keeps placeholders) -> factcheck_ar -> HUMAN_REVIEW (interrupt; script editor) -> tts_en/tts_ar -> AUDIO_REVIEW (interrupt; listen to voice + music preview, approve or re-record after changing voice/music in Admin) -> build_props -> render_en/render_ar -> mix_audio -> index_script -> done`. Status of each node is stored so the UI can show progress. Editing a scene after approval re-runs from `factcheck` for changed scenes only.

**Render:** `npx remotion render src/index.ts QuarterlyVideo out.mp4 --props=props.json` (run in `video/`), then FFmpeg: voice + music at `MUSIC_VOLUME` with sidechain ducking, `-c:v copy`. Also a 15 s social cut (intro + KPI scene).

**Summary (disclosure style):** per company + period, passages from the index (opening pages, statements, auditor's report, notes) -> ONE Gemini call (`summary_disclosure.md`): document facts (issuer, auditor, opinion, board approval), up to 10 key figures copied exactly as printed, a 100-200 word executive summary with `{{F1}}` / `{{F1.prior}}` / `{{F1.change}}` placeholders, 2-4 implications and a full analysis, all citing passages -> ONE Arabic call (`summary_translate_ar.md`). Python checks each figure is printed in its cited passage, computes YoY changes, fills placeholders and flags stray numbers. The page shows the key-figures table with page/note links, and each source can be downloaded as its page extract (`/api/documents/{id}/pages`) or the full document (`/api/documents/{id}/download`).

**Video Q&A:** search script chunks (with timestamps) + document chunks -> top 8 -> Gemini answers ONLY from them, returns `{answer, citations[], timestamp|null}`; below a score threshold reply "not covered" and log.

**Stock agent:** resolve company -> ticker from `backend/app/data/qse_tickers.json` (build in Step 10: ~55 QSE companies, EN + AR names, aliases) -> tools `get_quote`, `get_history(days)`, `search_news` -> compute changes in Python -> Gemini writes 1-2 sentences copying figures verbatim -> append "Source: X, as of HH:MM Doha time, delayed" -> log raw JSON.

## Admin settings (SQLite `Setting` table, key/value JSON)
`voice_engine`, `voice_en`, `voice_ar`, `voice_rate`, `music_track`, `music_volume`, `target_seconds`, `languages` (["en","ar"]), `captions`, `social_cut`, `require_review`, `require_audio_review`, `enforce_length`, `llm_model`, `arabic_digits` ("western"|"eastern"). Custom voices (SILMA, stretch) require a consent checkbox and store the reference clip under `data/voices/`. Voices copied from YouTube or other people's recordings are not allowed. NotebookLM: allow uploading an MP4 made in NotebookLM and attaching it to a quarter as an alternative video (no API exists to generate it).

## Commands

```bash
# back end (from repo root)
backend\.venv\Scripts\activate
uvicorn backend.app.main:app --reload --port 8000

# front end
cd frontend && npm run dev          # http://localhost:3000

# video preview / render
cd video && npx remotion studio
cd video && npx remotion render src/index.ts QuarterlyVideo ../outputs/videos/test.mp4 --props=../outputs/videos/test.props.json
```

## Definition of done for the POC
- From the dashboard: pick Q2 2026 -> Generate -> edit a scene -> Approve -> watch EN and AR videos (2-3 min) with captions, music and brand.
- Summary page shows a cited executive summary in EN and AR.
- Q&A beside the video answers "Why was there a loss in Q2?" with a citation and a timestamp link.
- Stock chat answers "What is Industries Qatar trading at?" with price, source and time; refuses gracefully if the source is down.
- Admin can switch voices per language and the next render uses them.
