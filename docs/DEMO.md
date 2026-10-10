# D-Storify POC: demo guide

A 5-minute walkthrough of the quarterly-results POC, what to prepare beforehand, what it cannot do yet, and what the paid upgrades would change.

All figures in the demo are **Industries Qatar's published 2026 results, used as sample data**. Every screen shows a "Demo data" badge. Do not present them as D-Storify's own results.

---

## Before the demo (allow 1 hour)

Gemini's free tier and video rendering are the two slow parts, so do them in advance.

1. **Check Gemini quota.** Each free model allows about 20 requests a day; when one runs out the app switches to the next model in `GEMINI_FALLBACK_MODELS` (`.env`). Admin → *Language model* lists any model that is used up and when it resets. Don't run the full smoke test on demo day: it uses about 10 requests.
2. **Start the servers** (two terminals, from the project folder):
   ```bat
   backend\.venv\Scripts\activate
   uvicorn backend.app.main:app --port 8000 --reload --reload-dir backend/app --reload-exclude "backend/app/store/*"
   ```
   ```bat
   cd frontend
   npm run dev
   ```
   Open http://localhost:3000 and confirm the green **API connected** badge.
3. **Render the Q2 2026 video at least 40 minutes early.** Dashboard → Q2 2026 → *Generate video* → review → *Approve*. English and Arabic take about 8-15 minutes each to render.
4. **Generate the summary** (Summary → *Generate summary*, about a minute) if it is not already there.
5. **Ask each demo question once** (the Q&A questions and stock questions below). Answers are cached, so on stage they appear instantly and use no quota.
6. **Quick health check** (no Gemini requests, about a minute):
   ```bat
   backend\.venv\Scripts\python -m backend.tests.smoke --offline
   ```
   Every line should say PASS or SKIP.

---

## The 5-minute walkthrough

| Time | Screen | Show | Say |
| --- | --- | --- | --- |
| 0:00 | **Dashboard** | The Q1, Q2 and H1 2026 cards. Q2 shows a red *net loss of QR 518 m* and a *derived* tag. | "We start from the company's results file. Q2 isn't published on its own; it's H1 minus Q1, so the app marks it as derived and never calls it 'reported'." |
| 0:30 | **Script editor** (`/scripts/iqcd-q2-2026`) | Locked figure chips in English and Arabic. Type "about 600 million" into a scene: a red warning appears and *Approve* is disabled. Delete it. | "Gemini writes the words, never the numbers. Every figure is a locked value from the data file, and anything typed by hand is blocked." |
| 1:15 | **Script editor** | The length bar (EN/AR, 2-minute minimum), *Regenerate scene*, the progress panel. | "An editor reviews every scene before anything is rendered. One click re-writes a single scene." |
| 1:45 | **Video page** (`/videos/iqcd-q2-2026`) | Play 15 seconds of English, switch to العربية (right-to-left layout, Arabic voice), point at the captions, KPI cards and the red loss bar. | "One approval produces both languages: branded scenes, word-by-word captions, licensed music ducked under the voice, and a 15-second social cut." |
| 2:30 | **Q&A panel** (beside the player) | Click *Why was there a loss in Q2?* → cited answer → click *Explained at m:ss*; the video jumps to that scene. Then ask an off-topic question. | "Answers come only from this video's script and the results PDFs, with sources. Questions outside them are declined." |
| 3:15 | **Summary** | Executive view, click a citation → the source passage and *Open PDF at page N*. Switch to Investor and العربية. | "Every point is cited to a PDF page, and the app checks that each number appears in the cited passage." |
| 4:00 | **Stock chat** | *What is Industries Qatar trading at?* → price, change, source and Doha time, delayed/closed badge. Then *كم سعر سهم صناعات قطر؟* | "Prices come only from the price feed, with the time they were valid. The model only phrases the sentence, and every number is checked." |
| 4:40 | **Admin** | Arabic voice picker with *Preview*, music track and licence credit, review switch, NotebookLM import. | "Voices, music, length and model are settings, not code. The next render uses them." |

### Questions to have ready

- Video Q&A: *Why was there a loss in Q2?*, *How strong is the balance sheet?*, and one off-topic question (e.g. *Who won the World Cup?*).
- Stock chat: *What is Industries Qatar trading at?*, *Compare QNB and Ooredoo over the last 3 months*, *كم سعر سهم صناعات قطر؟*

### If something goes wrong on stage

| Problem | What to do |
| --- | --- |
| A Gemini answer is slow or fails ("high demand", quota) | Use the cached demo questions. The stock chat still answers without Gemini (marked *Template answer*). |
| Stock source not responding | The bot says it can't fetch the price. That is the intended behaviour; point it out. |
| A render is still running | Show the progress panel (live frame counts) and switch to an already-rendered quarter (Q1 2026). |

---

## Known limits of the POC

- **Gemini free tier:** about 20 requests per day per model, about 10 per minute, and occasional "high demand" errors. The app falls back across models and caches answers, but a busy demo day can still run out.
- **Render time:** 8-15 minutes per language on a laptop (CPU only). Rendering happens after approval, in the background.
- **Prices:** Yahoo Finance via yfinance is unofficial and delayed, has no service guarantee, and can change without notice. QSE trades Sunday-Thursday, 09:30-13:15 Doha time; outside those hours the bot shows the last close and says the market is closed.
- **Demo data:** Q2 2026 is derived (H1 minus Q1); H1 revenue is rounded in the source, so Q2 revenue is approximate. The narrative drivers in the data file describe H1 and are not tagged by quarter. The Arabic driver texts were translated for the POC and should be checked by an Arabic speaker.
- **Arabic video length:** the Qatari Arabic voices speak more slowly, so Arabic videos run about 20-30 % longer than English (3:30-4:00 for a 2:50 English video). The minimum is 2 minutes; there is no maximum.
- **Summary figures** are copied exactly from the PDFs, so financial-statement figures appear in QR thousand (e.g. "QR 5,106,461 thousand"), not rounded.
- **Q&A** decides "not covered" by a relevance score calibrated on this demo's documents; new documents may need re-tuning. Some Arabic off-topic questions reach Gemini, which declines them.
- **Not included:** NotebookLM videos must be made by hand and imported (there is no NotebookLM API); custom cloned voices (SILMA) are only stored with consent, not synthesised; there is no login or multi-user access control.
- **Remotion licence:** Remotion is free for companies of up to 3 people; a larger company needs a Remotion company licence.

---

## What the paid upgrades change

The POC keeps each provider behind a small interface, so these plug in without rewriting the app.

| Upgrade | Replaces | What changes |
| --- | --- | --- |
| **Claude or OpenAI API** | Gemini free tier (`services/llm.py`) | No 20-a-day limit; faster, more consistent scripts, Arabic and answers; the stock agent can use full tool calling. |
| **ElevenLabs or OpenAI TTS** | edge-tts (`services/tts/`) | More natural, brandable voices; consented custom voice cloning; commercial voice licence. |
| **HeyGen (or similar) avatar** | — (new scene type) | A presenter avatar reading the approved script, in both languages. |
| **Licensed QSE market-data feed** | yfinance (`services/stock.py`) | Real-time or officially delayed prices with a service agreement, company actions, and dividends. |
| **Cloud rendering** (Remotion Lambda or a render server) | Laptop CPU rendering | Minutes become under a minute per video, several videos at once. |
| **pgvector / managed vector database** | Local ChromaDB | Many companies and years of documents, shared by several users. |
