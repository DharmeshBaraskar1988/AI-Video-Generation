# D-Storify POC - build steps (2 days)
Work in order. In VS Code, open the project folder, start Claude Code, and paste each step's prompt. Check the result before moving on. Claude Code reads CLAUDE.md automatically.

## Step 0 - Set up the machine
**When:** Day 1 · 30 min  
**Who:** You  
**Goal:** Check the computer, install free tools, test voices, download sample PDFs.

**Do this**

```text
1. Unzip the pack to a folder such as C:\dstorify-poc
2. Double-click setup\check_system.bat and read the report
3. Double-click setup\install.bat (paste your Gemini key when asked)
4. Play outputs\voice_test\*.mp3 and pick your EN and AR voices
```

**Creates**

- `setup/system_report.txt`
- `.env`
- `backend/.venv/`
- `outputs/voice_test/*.mp3`
- `data/documents/*.pdf`

**Result you should see:** All checks green; four voice samples (2 English, 2 Qatari Arabic); three Industries Qatar PDFs in data/documents; GEMINI_MODEL filled in .env.

**Check:** Voice samples play; .env has GEMINI_API_KEY and GEMINI_MODEL.

## Step 1 - Scaffold the app
**When:** Day 1 · morning  
**Who:** Claude Code  
**Goal:** Back end, front end and database skeleton running together.

**Prompt for Claude Code**

```text
Read CLAUDE.md. Do Step 1 of docs/BUILD_STEPS.md: create the FastAPI back end in backend/app (main.py with CORS for FRONTEND_URL, config.py loading .env, db.py with the SQLModel tables listed in CLAUDE.md, a /api/health route, and a static mount for /outputs). Create the Next.js app in frontend/ (TypeScript, App Router, Tailwind, shadcn/ui) with a left navigation for Dashboard, Scripts, Videos, Summary, Chat and Admin, styled with the colours in data/brand/brand.json and the logo. Add a root README with run commands for Windows. Use the existing backend/.venv. Stop when both servers run and the dashboard shows 'API connected'.
```

**Creates**

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/db.py`
- `frontend/app/layout.tsx`
- `frontend/app/page.tsx`
- `README.md`

**Result you should see:** http://localhost:3000 shows the D-Storify shell with navigation and a green 'API connected' badge from http://localhost:8000/api/health.

**Check:** Both servers start without errors; the SQLite file appears in backend/app/store.

## Step 2 - Quarter data on the dashboard
**When:** Day 1 · morning  
**Who:** Claude Code  
**Goal:** Load and validate quarter files; show the KPI picture.

**Prompt for Claude Code**

```text
Do Step 2: add services/quarters.py to load every file in data/quarters, validate it with Pydantic, and expose GET /api/quarters and GET /api/quarters/{company}/{period}. Mark derived values. On the dashboard, list companies and quarters with revenue, net profit and EPS cards (loss shown in the loss colour, 'derived' note where derived is true, 'Demo data' badge when the file's _note says DEMO). Add a 'Generate video' button per quarter (disabled for now).
```

**Creates**

- `backend/app/services/quarters.py`
- `backend/app/api/quarters.py`
- `frontend/app/page.tsx`
- `frontend/components/QuarterCard.tsx`

**Result you should see:** Dashboard shows Q1 2026 (revenue 4,166, profit 734), H1 2026 and Q2 2026 (derived, net loss 518) with a Demo data badge.

**Check:** GET /api/quarters returns the three periods; Q2 shows derived: true.

## Step 3 - Script graph: draft, fact-check, translate
**When:** Day 1 · morning  
**Who:** Claude Code  
**Goal:** Generate an English + Arabic scene script with every number verified.

**Prompt for Claude Code**

```text
Do Step 3: build services/llm.py (Gemini via google-genai, model from GEMINI_MODEL, JSON output, rate limit from GEMINI_MAX_RPM, tenacity retry, SQLite cache), services/factcheck.py (fill {{placeholders}} with Python-formatted EN/AR strings, flag any digit the model typed), prompts/script.md and prompts/translate_ar.md, and graphs/video_graph.py with the nodes load_quarter -> gather_context -> draft_script -> factcheck -> translate_ar -> factcheck_ar -> human_review (LangGraph interrupt). Expose POST /api/scripts (body: company, period) which runs until human_review and stores the script JSON (schema in CLAUDE.md). Target 350-450 English words, 7 scenes, broadcast tone, honest about losses. Enable the dashboard's Generate button to call it and open /scripts/{id}.
```

**Creates**

- `backend/app/services/llm.py`
- `backend/app/services/factcheck.py`
- `backend/app/prompts/script.md`
- `backend/app/prompts/translate_ar.md`
- `backend/app/graphs/video_graph.py`
- `backend/app/api/scripts.py`

**Result you should see:** Clicking Generate on Q2 2026 produces a 7-scene script in English and Arabic; the check report says all numbers match the data file.

**Check:** Script JSON in outputs/scripts/ has checks.numbers_ok == checks.numbers_total and no stray_numbers.

## Step 4 - Script editor
**When:** Day 1 · afternoon  
**Who:** Claude Code  
**Goal:** Review and edit every scene before anything is rendered.

**Prompt for Claude Code**

```text
Do Step 4: build /scripts/[id] with ScriptEditor: one card per scene showing type, English text (left) and Arabic text (right, dir=rtl, Arabic font), placeholders rendered as locked chips with their formatted value, a word count and estimated seconds per scene (150 wpm EN), and an overall length bar against target_seconds. Users can edit wording, reorder scenes, regenerate one scene (LLM call for that scene only), and Save (PUT /api/scripts/{id}) which re-runs factcheck and shows any stray numbers inline. Approve (POST /api/scripts/{id}/approve) resumes the graph past human_review.
```

**Creates**

- `frontend/app/scripts/[id]/page.tsx`
- `frontend/components/ScriptEditor.tsx`
- `backend/app/api/scripts.py`

**Result you should see:** You can rewrite a sentence, see the length update, get a warning if you type a number by hand, then Approve.

**Check:** Typing '600 million' into a scene shows a stray-number warning; removing it clears the warning.

## Step 5 - Voice with word timings
**When:** Day 1 · afternoon  
**Who:** Claude Code  
**Goal:** Narrate approved scripts in the chosen English and Arabic voices.

**Prompt for Claude Code**

```text
Do Step 5: build services/tts/base.py (interface: synthesize(text, voice, rate) -> audio path + word timings) and services/tts/edge.py using edge-tts Communicate with boundary='WordBoundary', saving MP3 and a words JSON (offsets converted to seconds). Add the graph nodes tts_en and tts_ar after approval, one audio file per language with a short pause between scenes, and record each scene's start/end from its first/last word. Read voices from the Setting table (default from .env). Add a stub tts/silma.py that raises 'not installed'.
```

**Creates**

- `backend/app/services/tts/base.py`
- `backend/app/services/tts/edge.py`
- `backend/app/services/tts/silma.py`
- `outputs/audio/*.mp3`
- `outputs/audio/*_words.json`

**Result you should see:** After Approve, outputs/audio has iqcd-q2-2026_en.mp3 (~2:30) and _ar.mp3 with word-timing files; the script page plays both.

**Check:** Word timings increase monotonically and the last word ends within 1 s of the audio length.

## Step 6 - Remotion video templates
**When:** Day 1 · evening  
**Who:** Claude Code  
**Goal:** Branded animated scenes driven only by the props JSON.

**Prompt for Claude Code**

```text
Do Step 6: create the Remotion project in video/ (npx create-video@latest, blank TypeScript template; pin the installed version). Build QuarterlyVideo that reads props (schema in CLAUDE.md) and plays the audio. Scenes: Intro (logo, company, quarter), KpiCards (CountUp numbers, green/red ChangeArrow), TrendChart (animated bars for net profit history, loss bars below zero in loss colour), Drivers (3-4 bullet cards from narrative_drivers), Segments (revenue share donut), Outlook, Outro (logo, 'Demo data' line when demo is true). Captions component highlights the current word from props.words. RTL mode mirrors layouts and uses IBM Plex Sans Arabic. 1920x1080, 30 fps. Add a sample props file and make `npx remotion studio` preview it.
```

**Creates**

- `video/src/Root.tsx`
- `video/src/QuarterlyVideo.tsx`
- `video/src/scenes/*.tsx`
- `video/src/components/*.tsx`
- `video/src/theme/*.ts`
- `video/sample.props.json`

**Result you should see:** Remotion Studio previews a full branded video from the sample props in English and Arabic layouts.

**Check:** Arabic scenes read right to left; the loss bar is red and below the zero line.

## Step 7 - One-click render and video page
**When:** Day 1 · evening  
**Who:** Claude Code  
**Goal:** Approve a script and watch the finished videos in the app.

**Prompt for Claude Code**

```text
Do Step 7: services/render.py builds the props per language from the script, word timings and brand.json, runs `npx remotion render` in video/ via subprocess, then FFmpeg mixes the music track at MUSIC_VOLUME with sidechain ducking and makes a 15-second social cut. Add graph nodes build_props, render_en, render_ar, mix_audio; track progress per node in SQLite and stream it to the UI (polling is fine). Build /videos/[id] with an HTML5 player, EN/AR switch, captions, download links and the progress timeline. Dashboard shows finished videos.
```

**Creates**

- `backend/app/services/render.py`
- `backend/app/api/videos.py`
- `frontend/app/videos/[id]/page.tsx`
- `frontend/components/VideoPlayer.tsx`
- `outputs/videos/*.mp4`

**Result you should see:** MILESTONE: the Q2 2026 video plays in English and Arabic, about 2.5 minutes each, with voice, music, captions and brand.

**Check:** Changing one scene, saving and approving re-renders and the change is audible.

## Step 8 - Documents index and summary
**When:** Day 2 · morning  
**Who:** Claude Code  
**Goal:** Cited executive summary from the results PDFs.

**Prompt for Claude Code**

```text
Do Step 8: services/rag.py ingests every PDF in data/documents (pypdf text per page, pdfplumber tables rendered as markdown), chunks to ~600 tokens with {file, page, section} metadata, embeds with sentence-transformers multilingual-e5-small ('passage: ' prefix) into Chroma, and searches with 'query: ' prefix plus a keyword boost. POST /api/documents/ingest, GET /api/documents. Summary: one Gemini call per section, then an executive summary EN + AR with [file p.N] citations (prompts/summary_section.md, summary_exec.md), cached. Build /summary with an Executive / Investor toggle, EN/AR tabs and clickable citations. Also switch the video graph's gather_context to use the index.
```

**Creates**

- `backend/app/services/rag.py`
- `backend/app/api/documents.py`
- `backend/app/prompts/summary_*.md`
- `frontend/app/summary/page.tsx`

**Result you should see:** The summary page shows a one-page H1 2026 summary in English and Arabic, each point cited to a PDF page.

**Check:** Clicking a citation shows the source passage; numbers match the PDF.

## Step 9 - Video Q&A panel
**When:** Day 2 · morning  
**Who:** Claude Code  
**Goal:** Ask questions beside the video and jump to the answer.

**Prompt for Claude Code**

```text
Do Step 9: after rendering, index each scene's script text with its start time (metadata kind=script, video_id, lang). graphs/qa_graph.py: retrieve script chunks for this video first, then document chunks; keep top 8; Gemini answers only from them (prompts/qa.md) returning {answer, citations, timestamp}; below the score threshold answer 'not covered in this video or the documents' and log to QALog. POST /api/qa. Add QAPanel beside the player with 4 suggested questions, EN/AR input, citations, and 'Explained at m:ss' links that seek the player. Optional 'Listen' button synthesizes the answer with the current voice.
```

**Creates**

- `backend/app/graphs/qa_graph.py`
- `backend/app/api/qa.py`
- `backend/app/prompts/qa.md`
- `frontend/components/QAPanel.tsx`

**Result you should see:** Asking 'Why was there a loss in Q2?' gives a short cited answer and a link that jumps the video to that scene.

**Check:** An off-topic question returns the 'not covered' reply.

## Step 10 - Stock chatbot
**When:** Day 2 · afternoon  
**Who:** Claude Code  
**Goal:** Precise, sourced answers about QSE stocks.

**Prompt for Claude Code**

```text
Do Step 10: create backend/app/data/qse_tickers.json with the QSE-listed companies (English name, Arabic name, aliases, Yahoo symbol ending .QA); verify each symbol with yfinance and drop ones that return no data. services/stock.py: get_quote, get_history(days) with a 60 s cache; all percentage changes computed in Python. graphs/stock_agent.py: Gemini tool calling to resolve the company and pick tools; search_news via ddgs for 'why' questions. The final answer copies numbers verbatim and appends 'Source: Yahoo Finance via yfinance, as of HH:MM Doha time, may be delayed'. If the tool fails, say the price can't be fetched right now. Log every answer with raw JSON. Build /chat with EN/AR support and example questions.
```

**Creates**

- `backend/app/data/qse_tickers.json`
- `backend/app/services/stock.py`
- `backend/app/graphs/stock_agent.py`
- `backend/app/api/stock.py`
- `frontend/app/chat/page.tsx`
- `frontend/components/StockChat.tsx`

**Result you should see:** 'What is Industries Qatar trading at?' returns the latest price with source and time; Arabic questions work too.

**Check:** Disconnect the internet: the bot says it can't fetch the price instead of guessing.

## Step 11 - Admin settings
**When:** Day 2 · afternoon  
**Who:** Claude Code  
**Goal:** Change voices, music, length and model without touching code.

**Prompt for Claude Code**

```text
Do Step 11: build /admin backed by GET/PUT /api/settings (keys in CLAUDE.md). Voice engine select, English and Arabic voice dropdowns filled from edge-tts --list-voices filtered to en-* and ar-*, a Preview button that synthesizes a test sentence, speed slider, music track upload (mp3 to data/music with a licence note field), target length, languages, captions, social cut, require review, LLM model (list from Gemini models API), Arabic digits style. Custom voice (stretch, SILMA): name + clip upload + mandatory consent checkbox. 'Import NotebookLM video': upload an MP4 and attach it to a quarter as an alternative video shown on the video page.
```

**Creates**

- `backend/app/api/settings.py`
- `frontend/app/admin/page.tsx`
- `frontend/components/VoicePicker.tsx`

**Result you should see:** Switching the Arabic voice from Moaz to Amal and re-rendering changes the narration.

**Check:** Settings survive a server restart (stored in SQLite).

## Step 12 - Test and demo
**When:** Day 2 · evening  
**Who:** You + Claude Code  
**Goal:** Run everything end to end and prepare the demo.

**Prompt for Claude Code**

```text
Do Step 12: write a smoke test script (backend/tests/smoke.py) that runs Q1 2026 and Q2 2026 through script generation, factcheck, TTS and render, ingests the PDFs, asks 3 Q&A questions and 3 stock questions, and prints a pass/fail table. Fix anything that fails. Then write docs/DEMO.md: a 5-minute demo walkthrough, known limits (free-tier rate limits, delayed prices, demo data), and what the paid upgrades change.
```

**Creates**

- `backend/tests/smoke.py`
- `docs/DEMO.md`

**Result you should see:** All smoke checks pass; a 5-minute demo script is ready.

**Check:** Fresh clone + install.bat + smoke.py passes on your machine.
