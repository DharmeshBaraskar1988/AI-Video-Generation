# D-Storify Quarterly Results POC

Quarterly results -> branded AI video (English + Arabic), cited summary, video Q&A and a live QSE stock chatbot. Free stack, two-day build with Claude Code.

## Start here (Windows)

1. Unzip this folder to a short path, e.g. `C:\dstorify-poc`.
2. Double-click **`setup\check_system.bat`** - checks memory, disk, Node.js, Python, FFmpeg, Git and network access. Changes nothing.
3. Double-click **`setup\install.bat`** - installs the free tools that are missing (Windows may ask permission), creates the Python environment, downloads the embedding model, tests 4 voices, downloads the sample PDFs and creates `.env`. Have your free Gemini key ready: https://aistudio.google.com/apikey
   - If it says Python is not on PATH yet, close the window, open a new one and run it again.
4. Listen to `outputs\voice_test\*.mp3`.
5. Add a royalty-free music track as `data\music\calm_corporate.mp3`.
6. Open the folder in VS Code, start Claude Code and follow **`docs\BUILD_STEPS.md`** from Step 1 (or open `docs\architecture.html` in a browser, Build steps tab, and copy each prompt).

## Run the app (Windows)

Double-click **`start.bat`** to open both servers in their own windows (the back end reloads itself when code changes). Or open two terminals in the project folder:

**Back end** (FastAPI, http://localhost:8000):

```bat
backend\.venv\Scripts\activate
uvicorn backend.app.main:app --port 8000 --reload --reload-dir backend/app --reload-exclude "backend/app/store/*"
```

**Front end** (Next.js, http://localhost:3000):

```bat
cd frontend
npm install
npm run dev
```

Open http://localhost:3000. The dashboard shows a green **API connected** badge when the back end is running. Health check: http://localhost:8000/api/health. API docs: http://localhost:8000/docs.

- The SQLite database is created at `backend\app\store\dstorify.db` on first start.
- Brand colours and logo come from `data\brand\`; `npm run dev` copies them into the front end automatically.
- The front end calls the API at `NEXT_PUBLIC_API_URL` (set in `frontend\.env.local`, default `http://localhost:8000`).

**Video templates** (Remotion Studio, http://localhost:3100):

```bat
cd video
npm install
npm run dev
```

Studio shows `QuarterlyVideo` (English sample) and `QuarterlyVideoArabic` (right-to-left sample). To refresh the samples from the latest Q2 2026 script (re-records the sample narration):

```bat
backend\.venv\Scripts\python -m backend.scripts.make_sample_props
```

`npm run stills -- <folder>` renders one still per scene in both languages, for a quick visual check.

**Rendering** happens automatically after you approve a script (narration → Remotion → FFmpeg music mix → 15 s social cut). It needs FFmpeg (`winget install Gyan.FFmpeg`) and uses Remotion's own headless browser (downloaded once, ~120 MB; set `REMOTION_BROWSER` to use another). Expect roughly 8-15 minutes per language on a laptop. Music comes from `data/music` (see `LICENSES.txt`; CC BY tracks are credited in the outro and on the video page).

## Test and demo

```bat
backend\.venv\Scripts\python -m backend.tests.smoke --offline      quick check, no Gemini requests
backend\.venv\Scripts\python -m backend.tests.smoke --skip-render  scripts, narration, Q&A, stock (~10 Gemini requests)
backend\.venv\Scripts\python -m backend.tests.smoke                full run incl. 4 renders (~50 min)
```

The smoke test works on separate `smoke-...` copies, so scripts waiting for your review are not touched. See `docs/DEMO.md` for the 5-minute demo walkthrough, known limits and paid upgrades.

## What is in the pack

| Path | What it is |
| --- | --- |
| `CLAUDE.md` | Full project spec Claude Code reads automatically: rules, stack, data contracts, pipelines |
| `docs/BUILD_STEPS.md` | 13 steps with the exact prompt, files created, expected result and check |
| `docs/architecture.html` | Clickable architecture: runtime flows, admin settings mock, build steps |
| `setup/` | System check, installer, Gemini model picker, voice test texts |
| `data/quarters/iqcd_2026.json` | Demo quarter data (Industries Qatar 2026, with sources) |
| `data/brand/` | Placeholder D-Storify logo and colours |
| `backend/requirements.txt` | Python packages |
| `.env.example` | All settings with defaults |

## Free tools used

Node.js LTS, Python 3.12, FFmpeg, Git (installed by `install.bat`); Python packages: FastAPI, LangGraph, google-genai (Gemini free tier), sentence-transformers, ChromaDB, pypdf, pdfplumber, edge-tts, yfinance, ddgs; Node packages (installed by Claude Code): Next.js, Tailwind, shadcn/ui, Remotion.

Demo data note: the sample numbers are Industries Qatar's published results, used only to test the pipeline. Do not publish videos presenting them as D-Storify's results.
