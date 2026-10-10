# D-Storify POC – Software Requirements & Dependencies

Oct 10, 2026 · @Dharmesh

## Overview and cost summary

The whole POC runs on free software and free service tiers; the only money you can spend today is the optional OpenAI key, used as a fallback when Gemini's free daily quota runs out.

D-Storify turns a company's quarterly results into a branded EN + AR video, a cited document summary, video Q&A and a QSE stock chatbot. Everything runs on one Windows machine: a Python back end (port 8000), a Next.js front end (port 3000) and a Remotion video renderer.

| Area | What we use | Cost today | Becomes paid when |
| --- | --- | --- | --- |
| Language model | Google Gemini (free tier) | Free, rate-limited | You need more than the free daily quota, or switch to OpenAI / Claude |
| LLM fallback | OpenAI (optional) | Paid per token, only if a key is set | Always paid when used |
| Embeddings + search | multilingual-e5-small + ChromaDB, local | Free | Moving to a hosted vector DB (pgvector, etc.) |
| Voice | Microsoft Edge neural voices (edge-tts) | Free | Switching to ElevenLabs / OpenAI TTS or a cloned voice |
| Video | Remotion + FFmpeg, local render | Free for individuals and small companies | Remotion needs a company licence for larger organisations |
| Stock prices | yfinance (Yahoo, delayed) | Free | A licensed real-time QSE feed for production |
| News | DuckDuckGo search (ddgs) | Free | A paid news API |
| Music | Kevin MacLeod tracks, CC BY 4.0 | Free with credit line | Buying a licensed music library |
| Front end / back end frameworks | Next.js, FastAPI, etc. | Free (open source) | Never (hosting costs only) |

For production, the items most likely to need budget are the stock data feed, the Remotion licence (depending on company size), a paid LLM, and hosting.

## System software (install on the machine)

Five programs are required and two are optional; all are free apart from Windows itself. `setup/check_system.bat` checks them and `setup/install.bat` installs the project packages.

| Software | Version in use | Used for | Cost |
| --- | --- | --- | --- |
| Windows 10/11 | Windows 11 | Development and demo machine | Licence already on the PC |
| Python | 3.12.10 | Runs the back end (API, agents, RAG, voice, stock tools) | Free, open source |
| Node.js + npm | 24.19.0 | Runs the Next.js front end and the Remotion video renderer | Free, open source |
| FFmpeg | 9.0.2 (winget Gyan.FFmpeg) | Mixes music under the voice, makes posters, music preview for audio review | Free, open source (LGPL/GPL) |
| Chrome / Chromium headless shell | Downloaded by Remotion | Remotion draws each video frame in a headless browser | Free |
| Git (optional) | any | Version control | Free |
| VS Code (optional) | any | Editor | Free |

Hardware: a normal laptop works. Rendering a 2-3 minute video takes a few minutes per language; the first run downloads the embedding model (~470 MB) and Remotion's browser.

## Back-end Python packages

All back-end packages are free and open source; they are listed in `backend/requirements.txt` and installed into `backend/.venv`.

| Package | Used for | Cost |
| --- | --- | --- |
| fastapi | Web API: quarters, scripts, videos, documents, Q&A, stock, settings | Free (MIT) |
| uvicorn[standard] | Runs the FastAPI server, auto-reload in development | Free (BSD) |
| python-multipart | File uploads (results PDFs, music, NotebookLM MP4, voice clips) | Free (Apache 2.0) |
| pydantic | Validates request bodies and quarter data files | Free (MIT) |
| python-dotenv | Loads settings from `.env` | Free (BSD) |
| httpx | HTTP client for external calls | Free (BSD) |
| sqlmodel | SQLite tables: Video, Script, Setting, QALog, StockLog, Document | Free (MIT) |
| langgraph | Video pipeline graph with script and audio review pauses, Q&A graph, stock agent | Free (MIT) |
| langgraph-checkpoint-sqlite | Saves graph state so a paused review survives a restart | Free (MIT) |
| langchain-core | Shared building blocks used by LangGraph | Free (MIT) |
| google-genai | Calls the Gemini language model | Free library (API usage: see AI services) |
| openai | Optional fallback language model | Free library (API usage is paid) |
| pypdf | Reads text from results PDFs, keeps page numbers for citations | Free (BSD) |
| pdfplumber | Reads tables from results PDFs | Free (MIT) |
| sentence-transformers | Runs the local embedding model for search | Free (Apache 2.0) |
| chromadb | Local vector store for document and script search | Free (Apache 2.0) |
| edge-tts | Text-to-speech with per-word timings for captions | Free (LGPL/GPL) |
| yfinance | QSE share prices and history (tickers ending `.QA`) | Free library (Yahoo data terms apply) |
| ddgs | DuckDuckGo news search for stock context (never prices) | Free (MIT) |
| mutagen | Reads MP3 length and metadata | Free (GPL) |
| tenacity | Retry with back-off for rate-limited LLM calls | Free (Apache 2.0) |

sentence-transformers pulls in PyTorch (CPU build), which is the largest download in the install.

## AI models and external services

Only two services need a key: Gemini (free key) and, optionally, OpenAI (paid); everything else runs locally or needs no account.

| Service | Used for | Key needed | Cost and limits |
| --- | --- | --- | --- |
| Google Gemini (Flash models) | Writes the script, Arabic translation, document summaries, Q&A answers, stock answer wording, document classification and figure extraction | Yes, free from aistudio.google.com/apikey | Free tier: about 10 requests/min and about 20 requests/day per model; the app switches to the next model in `GEMINI_FALLBACK_MODELS` when one runs out |
| OpenAI (gpt-4.1-mini by default) | Fallback language model when all Gemini daily quotas are used, or main model if `LLM_PROVIDER=openai` | Yes | Paid per token; optional, unused if the key is empty |
| intfloat/multilingual-e5-small | Embeddings for searching documents and video scripts (English + Arabic) | No (downloaded from Hugging Face once) | Free, runs on your CPU (MIT licence) |
| Microsoft Edge neural voices (via edge-tts) | Narration. EN: en-US-GuyNeural, en-GB-SoniaNeural. AR: ar-QA-MoazNeural, ar-QA-AmalNeural; others selectable in Admin | No | Free; uses Microsoft's online read-aloud service, so an internet connection is needed and it is not an official commercial API |
| Yahoo Finance (via yfinance) | QSE share price, change and history for the stock chatbot | No | Free; data is delayed and unofficial, meant for personal/research use, so not suitable as a production price source |
| oanor API (optional) | Alternative stock data source | Yes (`OANOR_API_KEY`) | Depends on the oanor plan; not required |
| DuckDuckGo search (via ddgs) | Recent news headlines as context in stock answers (never prices) | No | Free, unofficial, may rate-limit |
| Google NotebookLM | Optional: make a video in NotebookLM by hand and upload the MP4 as an alternative video | Google account | Free; there is no API, so it is a manual upload |

Numbers never come from the language model: figures are filled in by Python from approved data, so changing LLM provider does not change accuracy rules.

## Video project (Remotion, in `video/`)

Remotion is the one free tool with a company-size condition: it is free for individuals and small companies, but a larger company needs a paid Remotion Company License before using it commercially.

| Package | Version | Used for | Cost |
| --- | --- | --- | --- |
| remotion | 4.0.534 | Builds the video from React scenes (intro, KPI cards, trend chart, drivers, segments, outlook, outro) | Free for individuals and small teams; company licence for larger organisations ([licence terms](https://www.remotion.dev/license)) |
| @remotion/cli | 4.0.534 | `npx remotion render` and `remotion studio` preview | Same Remotion licence |
| @remotion/fonts | 4.0.534 | Loads fonts into the render | Same Remotion licence |
| react, react-dom | 19.2.3 | UI library Remotion scenes are written in | Free (MIT) |
| @fontsource/inter | 5.2.8 | English font in videos | Free (SIL Open Font License) |
| @fontsource/ibm-plex-sans-arabic | 5.2.8 | Arabic font in videos, right-to-left scenes | Free (SIL Open Font License) |
| typescript, eslint, prettier, @types/\* (dev only) | 5.9 / 9.39 / 3.8 | Type checking and code formatting | Free |

Confirm the current employee threshold on the Remotion licence page before any commercial use.

## Front-end packages (Next.js, in `frontend/`)

Every front-end package is free and open source; the only future cost is hosting the site.

| Package | Version | Used for | Cost |
| --- | --- | --- | --- |
| next | 15.5.27 | Web app: dashboard, scripts editor, videos, summary, chat, documents, admin pages | Free (MIT) |
| react, react-dom | 19.1.0 | UI library | Free (MIT) |
| tailwindcss, @tailwindcss/postcss | 4 | Styling, brand colours, right-to-left layout | Free (MIT) |
| shadcn, radix-ui | 4.21 / 1.7 | Ready-made accessible components (cards, buttons, dialogs) | Free (MIT) |
| class-variance-authority, cn, tw-animate-css | 0.7 / 0.4 / 1.4 | Component style variants and animations | Free (MIT/Apache) |
| lucide-react | 1.54 | Icons | Free (ISC) |
| typescript, eslint, eslint-config-next, @types/\* (dev only) | 5 / 9 / 15.5 | Type checking and linting | Free |

## Data, music, fonts and brand assets

All bundled assets are free to use; the music is free only with its credit line, which the video outro and video page show automatically.

| Asset | Location | Used for | Licence / cost |
| --- | --- | --- | --- |
| "Inspired" by Kevin MacLeod | `data/music/calm_corporate.mp3` | Default background music | CC BY 4.0: free, commercial use allowed, credit required |
| "Wholesome" by Kevin MacLeod | `data/music/wholesome.mp3` | Alternative background music | CC BY 4.0: free, credit required |
| Your own tracks | Uploaded in Admin, stored in `data/music/` | Background music | Must be royalty-free or licensed by you; add the credit to `LICENSES.txt` |
| Logo and brand colours | `data/brand/logo.svg`, `brand.json` | Video and UI branding | Your own brand assets |
| Industries Qatar demo data | `data/quarters/iqcd_2026.json` | Sample input, shown with a "Demo data" badge | Company's published results |
| Results PDFs / Markdown | Uploaded on the Documents page, stored in `data/documents/` | Source for figures, summaries and Q&A citations | Public company filings |
| QSE ticker list | `backend/app/data/qse_tickers.json` | Maps company names (EN + AR) to `.QA` tickers | Built for this project |
| Custom voice clips (SILMA, not installed) | `data/voices/` | Future cloned voices | Requires a consent checkbox; recordings copied from YouTube or other people are not allowed |

## Paid upgrade options (not built, interfaces ready)

Each paid option plugs into an existing interface, so it can be added later without redesigning the app; only the OpenAI fallback is wired in today.

| Upgrade | Replaces | Why upgrade | How it is billed | Status |
| --- | --- | --- | --- | --- |
| Claude or OpenAI LLM | Gemini free tier | No daily quota, steadier quality for scripts and Arabic | Per token used | OpenAI wired in as optional fallback; Claude not built |
| ElevenLabs or OpenAI TTS | edge-tts | More natural voices, official commercial terms | Per character, or monthly plan | Not built (`services/tts/base.py` interface) |
| SILMA / cloned voice | edge-tts | A custom brand voice | Self-hosted (GPU) or vendor plan | Stub only (`services/tts/silma.py`) |
| HeyGen avatar | Animated scenes only | A presenter on screen | Per video minute or monthly plan | Not built |
| Licensed QSE data feed | yfinance | Real-time, licensed prices allowed for production | Monthly data licence from the exchange or a vendor | Not built (`services/stock.py` interface) |
| pgvector / hosted vector DB | Local ChromaDB | Multi-user, server deployment | Database hosting | Not built (`services/rag.py`) |
| Remotion Company License | Remotion free licence | Required for larger companies using Remotion commercially | Per seat / per render plan | Needed only above the free threshold |
| Hosting (server + domain) | Local laptop | Make it available to users | Monthly cloud hosting | Not set up |

Prices change often, so get current quotes from each vendor before budgeting; none are listed here.

## Configuration and install

One free key (Gemini) is all you need to run the POC; every other setting has a working default in `.env`.

**Settings in `.env`**

| Key | Purpose | Required |
| --- | --- | --- |
| `GEMINI_API_KEY` | Language model access (free key) | Yes |
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODELS`, `GEMINI_MAX_RPM` | Which Gemini model, fallbacks when a daily quota runs out, request rate limit | Filled automatically |
| `LLM_PROVIDER`, `OPENAI_API_KEY`, `OPENAI_MODEL` | Optional paid OpenAI fallback or main model | No |
| `EMBEDDING_MODEL`, `CHROMA_DIR` | Local search model and index folder | Default works |
| `TTS_ENGINE`, `VOICE_EN`, `VOICE_AR`, `VOICE_RATE` | Default voices and speed (Admin page overrides them) | Default works |
| `VIDEO_TARGET_SECONDS`, `MUSIC_TRACK`, `MUSIC_VOLUME` | Video length target and background music (Admin page overrides them) | Default works |
| `STOCK_SOURCE`, `OANOR_API_KEY`, `STOCK_CACHE_SECONDS` | Stock data source and 60 s cache | Default works |
| `BACKEND_PORT`, `FRONTEND_URL`, `DATABASE_URL` | Ports and SQLite database location | Default works |

**Install steps**

1. Run `setup\check_system.bat` to see what is missing.
2. Run `setup\install.bat`. It installs Node.js, Python 3.12, FFmpeg and Git with winget, creates `backend\.venv`, installs `backend\requirements.txt` (5-10 minutes the first time), creates `.env` and asks for the Gemini key.
3. Install the front-end and video packages: `cd frontend && npm install`, then `cd video && npm install`.
4. Start the back end: `backend\.venv\Scripts\activate`, then `uvicorn backend.app.main:app --reload --port 8000`.
5. Start the front end: `cd frontend && npm run dev`, then open http://localhost:3000.
6. In Admin, pick voices per language, music and video options.
