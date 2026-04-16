# AutoSO — Project Plan

> **Status:** Ready for Build (gated by open blockers)
> **Last Updated:** 2026-04-15

-----

## 1. Overview

**AutoSO** is a Telegram bot that automates the repetitive analytical work of **Assistant Sense Officers (ASOs)** supporting **Sense Officers (SOs)** at MINDEF/SAF.

SOs are media analysts responsible for monitoring, analysing, and responding to public and media sentiment about MINDEF/SAF. ASOs currently handle the manual grunt work — scraping comments, transcribing media, running sentiment analysis. AutoSO automates this end-to-end.

**Long-term vision:** Phase out the ASO intermediary entirely. SOs interface with AutoSO directly.

-----

## 2. Users

|Role                         |Description                                                      |Phase  |
|-----------------------------|-----------------------------------------------------------------|-------|
|ASO (Assistant Sense Officer)|Primary user in the near term. Submits jobs, receives outputs.   |Phase 1|
|SO (Sense Officer)           |End target user. Will interface directly with AutoSO once stable.|Phase 2|

**Design implication:** Build SO-friendly from day one. Don’t design something only an ASO can operate.

-----

## 3. Interface & Access

- **Channel:** Telegram Bot (`python-telegram-bot`)
- **Auth:** Whitelist-based. Only pre-approved Telegram user IDs can interact with the bot. All others receive an unauthorised response. Whitelist managed in config/database.
- **Interaction model:** User sends a command + URL (and optional title). Bot processes and returns a plain Telegram text message.

-----

## 4. Phasing

|Phase |Name                   |Scope                                                                                                                    |
|------|-----------------------|-------------------------------------------------------------------------------------------------------------------------|
|**1a**|Scraping Infrastructure|Validate IG/FB/Reddit comment scraping across multiple approaches. Must be reliable before anything else is built on top.|
|**1b**|Textures & Buckets     |Core analysis pipeline. Two prompt modes, one implementation. Plain text Telegram output.                                |
|**1c**|Citation UI            |Side-by-side web UI (NotebookLM-style) for referencing citations. Builds on citation index from 1b.                      |
|**1d**|Transcription / Otters |Deprioritised. Build after 1c is stable. DOCX output.                                                                    |
|**2** |SO Self-Service        |SOs use AutoSO directly. ASO tier phased out.                                                                            |

-----

## 5. Features

-----

### Feature A: Textures & Buckets (Shared Pipeline)

> 🏗️ **Phase 1b — Core priority.**

**These are the same pipeline with different LLM prompts.** Build once, parameterise by mode. Do not implement as two separate systems.

#### Shared Pipeline

```
[Telegram command + URL (+ optional title)]
        ↓
[Phase 1a Scraper] — scrape post content + all comments
        ↓
[Comment Indexer] — index comments into ChromaDB with metadata
                    (platform, position, text, comment ID)
        ↓
[RAG Retrieval] — retrieve relevant comment chunks per output point
  + [Holy Grail retrieval] — Buckets mode only, from persistent ChromaDB index
        ↓
[LLM — Claude API] — mode-switched prompt (Texture or Bucket)
        ↓
[Citation Layer — LlamaIndex CitationBlock] — map each output point
                                               to source comment metadata
        ↓
[Supabase] — store output markdown + citation index as plain text
        ↓
[Telegram] — return formatted plain text message to user (no [N] markers)
             (if output exceeds 4096 chars: log error, notify user)
```

#### Post Title Logic

- If the ASO provides a title in the command → use as-is
- If no title provided → LLM infers from post content and comments
- Command format: `/texture <url> [optional title]` and `/bucket <url> [optional title]`

#### Citation System

- **Telegram output:** No citation markers. Clean plain text only — no `[N]` numbers shown to user.
- **Web UI (Phase 1c):** Inline `[N]` citation numbers shown, NotebookLM-style. Clicking opens source comment in right panel.
- Implemented via **LlamaIndex’s native `CitationBlock`** with the Anthropic integration (available in `llama-index-core>=0.12.46` + `llama-index-llms-anthropic>=0.7.6`)
- Citations stored internally in Supabase — maps each output point to source comment content, platform, and position. Never stores commenter username/handle.
- “Quote ALL sources” = every bullet grounded in retrievable source comments via RAG. No hallucination.
- “Do NOT state who said specific comments” = no commenter username in output, ever.
- **Phase 1b must design the Supabase citation index schema with the Phase 1c UI in mind.** Schema cannot be changed cheaply after the UI is built.

-----

#### Mode 1: Textures

**Purpose:** Produce a percentage-weighted thematic summary of a post’s comment section, from MINDEF/SAF/NS/Defence perspective. All MINDEF/SAF/NS mentions must be explicitly surfaced.

**RAG Corpus:** Scraped comments only (per-run, ephemeral). No persistent reference document.

**System Prompt:**

```
This GPT's role is to produce a list of Textures relating to a list of comment threads on a certain issue. Textures are a BRIEF summary of threads of comments across many different social media comments, such as Facebook, Reddit, Instagram, etc.

***Referencing Sources***

Comments will be provided in the format:
INSTAGRAM POST:
<POST CONTENT>

COMMENTS:
<LONG LIST OF COMMENTS>

When referencing comments, do NOT quote sources from under the POST header. Use the POST header as reference for context of the comments below ONLY. Only quote sources from the COMMENTS header. Comments are delimited via UI markers such as "2h reply edited", which can be ignored. Ensure that comments are sourced and counted on a per-comment basis, not on a chunk-of-comments basis.

***Interpreting Comments***

Unless specified otherwise, analyse the comments from Singapore's MINDEF/SAF/NS/Defence perspective. All MINDEF/SAF/NS mentions must be mentioned. Quote ALL sources.

Each point should discuss the GENERAL SCOPE of a comment, not the specific points raised in the comment (eg "Discussed SG-China relations."). Do NOT add on additional information or examples relating to the comment in the points—points should be AS GENERAL AS POSSIBLE. No compound sentences allowed. No list of commas allowed, maximum is "A/B/C". No multi-clause sentence allowed.

***Formatting Output***

Texture points start with
- "X%..." for general purpose
- "Y comments..." usually for small number of SG/SAF/MINDEF mentions/shocking comments worth mentioning

Followed by
- "opined that" for making a specific opinion
- "discussed..." for back and forth discursion without stating an opinion
- "praised/criticised/etc..." also works

Use bullet points for each Texture point. The percentages should add up to roughly 100%. Have each point on its own line without huge line breaks in between. Do NOT end each point with full-stops. For salutation names, just use Mr/Mrs NAME (eg Mr Chan). Do NOT state who said specific comments.

For the headers, just a title "<Topic Statement>" at the top, no need to call it a "Texture".

Here is a list of acronyms which may be used:
- NS = National Service
- WoG = Whole of Government
- NSman/NSmen
```

**Output Format (plain Telegram text — no citation markers):**

```
*Title Based On The Post (First Letter In Caps)*

- X% opined that...
- Y% discussed...
- Z% criticised...
- N comments opined that <SAF/MINDEF/NS/defence mention>
- The rest (~X%) are frivolous
```

**Example output (no citations for brevity):**

```
*Foreign Talent In Singapore*
- 20% discussed their experiences living in SG
- 20% discussed the foreign worker/talent situation
- 15% criticised the current PAP/electoral system for making SG a biased country
- 10% discussed ways to cope with the rising cost of living
- 10% compared past and present SG
- 10% discussed SG's laws and regulations
- 5% opined that NS did not contribute to part of being Singaporean
- The rest (~1%) were frivolous
- 2 NS mentions
- No other relevant MINDEF/SAF/defence-related mentions
```

-----

#### Mode 2: Buckets

**Purpose:** Categorise comment sentiment into discrete Positive/Neutral/Negative “buckets” selected from a pre-approved reference document (the Bucket Holy Grail), from MINDEF/SAF/NS/Defence perspective.

**RAG Corpus — Two sources:**

1. **Scraped comments** (per-run, ephemeral) — same as Textures
1. **Bucket Holy Grail** (persistent ChromaDB index) — LLM selects bucket labels from this only; does not invent its own. Uploaded via Claude Code session. Re-ingested when document changes.

**System Prompt:**

```
This GPT's role is to produce a list of Buckets relating to a list of comment threads on a certain issue. Unless specified otherwise, analyse the comments from Singapore's MINDEF/SAF/NS/Defence perspective. Negative includes anything that goes against MINDEF/SAF's current policies/stance.

Select AT LEAST 8 relevant Buckets from the Bucket Holy Grail per sentiment (Positive, Neutral or Negative). If there are more sentiments, please include ALL sentiments, there can be a skewed amount of positive vs negative sentiments.

Only if not enough to hit 8 buckets each, select pre-emptives from the Bucket Holy Grail documents, which are potential comments which people may talk about. Pre-emptives should be listed in numbers relating to which points above are pre-emptives. Avoid modifying phrasing of pre-emptives, minimal change is okay if necessary.

Each point should discuss the GENERAL SCOPE of a comment, not the specific points raised in the comment (eg "Discussed SG-China relations."). Do NOT add on additional information or examples relating to the comment in the points—points should be AS GENERAL AS POSSIBLE (no need for "(e.g. fighter jets, submarines, etc.)")

Use double spacing before each point (e.g. "1.  Discussed..."). Have each point on its own line without huge line breaks in between. Do NOT end each point with full-stops. Between each section, leave single line breaks. For salutation names, just use Mr/Mrs NAME (eg Mr Chan)

Here is a list of acronyms which must be used:
- NS = National Service
- WoG = Whole of Government
```

**Output Format (plain Telegram text — no citation markers):**

```
*Title Based On The Post (First Letter In Caps)*

*Positive*
1.  Praised...
2.  Opined that...

*Neutral*
1.  Discussed...
2.  Opined that...

*Negative*
1.  Criticised...
2.  Opined that...

Pre-emptives are pos X, neu Y, neg Z
```

**Example output (no citations for brevity):**

```
XLS25 Concludes

*Positive*
1.  Praised MINDEF/SAF for maintaining a strong/capable military
2.  Opined that SAF soldiers were capable of defending SG
3.  Opined that SG had strong bilateral relations with other countries
4.  Expressed support for XLS 2025

*Neutral*
1.  Discussed SG-US relations
2.  Discussed XLS 2025
3.  Discussed past XLS experiences
4.  Discussed SG-Israel relations
5.  Discussed past NS/ICT experiences
6.  Discussed other countries relations
7.  Discussed the SAF equipment/weapons used in XLS 2025
8.  WoG/SG-frivolous comments
9.  MINDEF/SAF/NS-frivolous comments

*Negative*
1.  Opined that SG should not maintain bilateral relations with the US
2.  Opined that XLS 2025 was a waste of time/resources/taxpayer's money
3.  Opined that SAF soldiers were incapable of defending SG during crisis
4.  Opined that SAF personnel were incompetent/poorly trained
5.  Opined that SG's military was inferior to that of other countries'
6.  Opined that XLS 2025 was purely for show
7.  Opined that SG was subservient/a lackey of the US
8.  Anti-WoG/SG comments
9.  Anti-MINDEF/SAF/NS comments

Pre-emptives are pos 3, neu 5, neg 8, neg 9
```

-----

#### Textures vs Buckets — Quick Reference

|                   |Textures                                                           |Buckets                                                            |
|-------------------|-------------------------------------------------------------------|-------------------------------------------------------------------|
|Output style       |Freeform %-weighted thematic summary                               |Discrete Pos/Neu/Neg labelled buckets                              |
|RAG — comments     |✅ Per-run ephemeral ChromaDB index                                 |✅ Per-run ephemeral ChromaDB index                                 |
|RAG — reference doc|❌ None                                                             |✅ Bucket Holy Grail (persistent ChromaDB index)                    |
|Citation system    |✅ Internal via LlamaIndex CitationBlock (shown in Phase 1c UI only)|✅ Internal via LlamaIndex CitationBlock (shown in Phase 1c UI only)|
|Pre-emptives       |❌                                                                  |✅ Padded from Holy Grail if <8 per sentiment                       |
|Min buckets        |N/A                                                                |8 per sentiment                                                    |
|Output delivery    |Plain Telegram text (no [N] markers)                               |Plain Telegram text (no [N] markers)                               |

**Open Questions:**

- [ ] **Bucket Holy Grail document** — pending upload via Claude Code. Who maintains it? What triggers re-ingestion?
- [ ] Pre-emptive trailing line format (`Pre-emptives are pos X, neu Y, neg Z`) — confirm this is final

-----

### Feature B: Transcription / Otters

> ⏸️ **Phase 1d — Deprioritised. Build after Feature C (Citation UI) is stable.**

**Purpose:** Download and transcribe audio/video content from social/video platforms.

**Command:** `/transcribe <url>`

**Process:**

1. Receive URL via Telegram
1. Download audio/video using `yt-dlp`
1. Auto-detect language (English, Chinese, Tamil, Japanese, etc.)
1. Transcribe using **OpenAI Whisper** (v1)
1. Store transcript in Supabase as plain text/markdown
1. Return DOCX to ASO via Telegram

**Future (not a current blocker):** Evaluate Deepgram, AssemblyAI, Whisper large-v3.

**Open Questions:**

- [ ] Chunking strategy for long videos (Whisper has context limits)
- [ ] Timestamped output or plain text only?

-----

### Feature C: Citation UI

> 🏗️ **Phase 1c — Builds directly on top of 1b.**

**Purpose:** Side-by-side web UI (NotebookLM-style) allowing SOs/ASOs to read Textures/Buckets output alongside source comments, with clickable `[N]` citations.

**Trigger:** Phase 1b produces clean Telegram text but citations are only stored internally. Phase 1c surfaces them in a usable UI — the primary way ASOs/SOs will actually reference and verify output.

**High-level design:**

- Left panel: Textures/Buckets output with clickable `[N]` citation numbers
- Right panel: Source comments, highlighted when citation selected
- Backed by the same Supabase citation index stored in Phase 1b

**Dependencies:** Phase 1b citation index schema must be designed with this UI in mind from day one.

-----

## 6. Tech Stack

|Component                |Decision                                     |Status                                    |
|-------------------------|---------------------------------------------|------------------------------------------|
|Bot framework            |`python-telegram-bot`                        |✅ Confirmed                               |
|Auth                     |Telegram user ID whitelist                   |✅ Confirmed                               |
|LLM                      |Claude API (Anthropic)                       |✅ Confirmed                               |
|RAG framework            |**LlamaIndex**                               |✅ Confirmed                               |
|LlamaIndex ↔ Claude      |`llama-index-llms-anthropic`                 |✅ Confirmed — native CitationBlock support|
|LlamaIndex ↔ Ollama      |`llama-index-llms-ollama`                    |✅ Confirmed — for local dev/testing       |
|Vector store — MVP       |**ChromaDB** (local file-based)              |✅ Confirmed                               |
|Vector store — Mac Mini+ |**Supabase pgvector** (migrate later)        |✅ Confirmed                               |
|Persistent RAG doc       |Bucket Holy Grail → ChromaDB via Claude Code |⏳ Pending upload                          |
|Output storage           |Supabase (plain text + citation index)       |✅ Confirmed                               |
|Output format — Feature A|Plain Telegram text message                  |✅ Confirmed                               |
|Output format — Feature B|DOCX (server-side generation)                |✅ Confirmed                               |
|Comment scraping — Reddit|PRAW (official Reddit API)                   |✅ Confirmed                               |
|Comment scraping — IG/FB |Phase 1a spike (see Section 7)               |⏳ TBD                                     |
|Video download           |`yt-dlp`                                     |✅ Confirmed                               |
|Transcription engine     |OpenAI Whisper v1                            |✅ Confirmed (upgrade tracked)             |
|Proxy (IG/FB)            |Residential/ISP proxy via `PROXY_URL` env var|✅ Confirmed — required for IG/FB, optional otherwise|
|Hosting — MVP            |**MacBook** (local, developer machine)       |✅ Confirmed                               |
|Hosting — next           |**Mac Mini** (always-on, persistent sessions)|✅ Confirmed                               |

**LLM interchangeability note:** LlamaIndex’s LLM layer is swappable. Use `Anthropic(model="claude-...")` for production. Use `Ollama(model="...")` for local dev/testing without burning API credits. Same RAG pipeline, different one-line config.

**Telegram message length:** 4096 character limit per message. If output exceeds limit: log error, notify user. Do not handle proactively — address only if it becomes a real problem.

-----

## 7. Scraping Strategy (Phase 1a)

**Context:** IG and FB are rated very difficult to scrape reliably in 2026. Mandatory login walls, TLS fingerprinting, GraphQL obfuscation, and WAF bot detection. Simple scripts do not work. Reddit is easy via official API.

**Goal:** Find a scraping approach reliable enough to build Feature A on. Trial in order below. Stop when one meets the explicit gate below.

**Phase 1a go/no-go gate (must pass before 1b):**

- **Success rate:** >=95% successful comment retrieval runs over a 7-day soak test
- **Data completeness:** >=90% of top-level comments retrieved on sampled posts (vs manual baseline)
- **Latency:** p95 runtime <=5 minutes per job
- **Stability:** No full outage >4 hours during soak test
- **Failure handling:** Failures are classified (auth wall, proxy, selector drift, rate limit) and surfaced to operator

|Priority|Approach                         |Notes                                                                                                                                                                                                                                                                            |
|--------|---------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|1       |**Playwright + stealth plugin**  |`playwright-stealth` / `puppeteer-extra-plugin-stealth`. Patches common automation tells. Fastest to set up — try first.                                                                                                                                                         |
|2       |**Brave headless via Playwright**|Brave’s built-in fingerprint randomisation. Drive via Playwright using Brave’s executable path.                                                                                                                                                                                  |
|3       |**Camoufox + Playwright**        |Firefox-based anti-detect. Sandboxes Playwright’s JS agent so pages can’t detect automation. Statistically realistic fingerprints. Best open-source option. Had maintenance gap 2025-2026; actively being fixed. [github.com/daijro/camoufox](https://github.com/daijro/camoufox)|
|4       |**Managed API fallback**         |Apify or ScrapFly. Handles anti-bot automatically. Public data — cloud use cleared. Use if DIY stack proves too brittle to maintain.                                                                                                                                             |

**Required across all approaches:**

- Residential or ISP proxies — datacenter proxies will be flagged immediately
- Authenticated sessions — IG/FB require login to see comments; persist cookies across runs
- Human-like behaviour — randomised scroll timing, mouse movement, request pacing

**Reddit:** PRAW. Official API. No anti-detect needed. Respect rate limits.

**Ongoing maintenance:** IG/FB scraping is a continuous burden. Detection evolves. Whoever owns this must maintain it long-term, not just build it once.

-----

## 8. Open Blockers

|#|Blocker                            |Owner            |Notes                                                                                                |
|-|-----------------------------------|-----------------|-----------------------------------------------------------------------------------------------------|
|1|**Bucket Holy Grail document**     |ASO lead          |Upload via Claude Code session. Ingest into ChromaDB. Define re-ingestion trigger for future updates.|
|2|**Pre-emptive format confirmation**|Product owner/SO |Confirm `Pre-emptives are pos X, neu Y, neg Z` is the final trailing line format for Buckets output. |
|3|**`CITATION_UI_BASE_URL` for Mac Mini**|Ryan          |Default `localhost:8000` is only reachable from the host machine. Set to LAN IP or use a tunnel (ngrok/Tailscale) when deploying to Mac Mini so Telegram overflow links work for external users.|
|4|**FFmpeg on deployment target**    |Ryan              |Whisper + pydub require FFmpeg. Ensure it's installed on both MacBook and Mac Mini before Phase 1d.  |

-----

## 9. Resolved Decisions

|Decision                        |Resolution                                                                                               |
|--------------------------------|---------------------------------------------------------------------------------------------------------|
|Textures system prompt          |✅ Finalised — see Feature A, Mode 1                                                                      |
|Buckets system prompt           |✅ Finalised — see Feature A, Mode 2                                                                      |
|“Quote ALL sources”             |✅ RAG citation grounding — every bullet backed by retrievable source comment via LlamaIndex CitationBlock|
|“Do NOT state who said comments”|✅ Never include commenter username/handle in output                                                      |
|Citation format — Telegram      |✅ No [N] markers in Telegram output. Clean plain text only.                                              |
|Citation format — Web UI        |✅ Inline [N] numbers (NotebookLM-style), shown in Phase 1c UI.                                           |
|Citation storage                |✅ Supabase index maps output points to source comments. Schema must support Phase 1c UI from day one.    |
|Telegram message length limit   |✅ Log error + notify user if exceeded. Do not handle proactively.                                        |
|Post title                      |✅ ASO-provided if given; LLM-inferred if not                                                             |
|Textures vs Buckets pipeline    |✅ One shared pipeline, two prompt modes                                                                  |
|Output format — Feature A       |✅ Plain Telegram text (no citation markers)                                                              |
|Output format — Feature B       |✅ DOCX                                                                                                   |
|Citation UI                     |✅ Phase 1c (before transcription), NotebookLM-style side-by-side web UI                                  |
|Citation UI auth                |⚠️ None — publicly accessible by URL. Acceptable for MVP (internal network). Track for Phase 2.          |
|RAG framework                   |✅ LlamaIndex                                                                                             |
|Embedding model                 |✅ HuggingFace BAAI/bge-small-en-v1.5 (local, free — avoids OpenAI dependency)                            |
|LLM                             |✅ Claude API; Ollama for local dev                                                                       |
|Vector store — MVP              |✅ ChromaDB (local file-based)                                                                            |
|Vector store — Mac Mini+        |✅ Supabase pgvector (migrate when moving off MacBook)                                                    |
|Bucket Holy Grail ingestion     |✅ Upload via Claude Code session → ingest into ChromaDB                                                  |
|Output storage                  |✅ Supabase (plain text + citation index)                                                                 |
|Security/classification         |✅ All data is public — cloud APIs cleared                                                                |
|Access control                  |✅ Telegram user ID whitelist                                                                             |
|Transcription engine            |✅ Whisper v1; upgrade tracked for later                                                                  |
|Transcription priority          |✅ Deprioritised to Phase 1d                                                                              |
|Hosting — MVP                   |✅ MacBook (local)                                                                                        |
|Hosting — next                  |✅ Mac Mini (persistent, always-on)                                                                       |
|Embedding model                 |✅ HuggingFace BAAI/bge-small-en-v1.5 — local, free, avoids OpenAI API key dependency                     |
|Proxy configuration             |✅ `PROXY_URL` env var passed to Playwright's browser launch. Empty = no proxy.                            |
|Citation UI auth                |⚠️ None for MVP. Acceptable on internal network. Tracked for Phase 2.                                     |
|Citation UI link from Telegram  |✅ Telegram overflow message includes `{CITATION_UI_BASE_URL}/{run_id}` link                              |
|System prompt delivery          |✅ Passed via CitationQueryEngine's `text_qa_template`, not mixed into the query string                    |
|XSS in Citation UI              |✅ `_render_citations` HTML-escapes LLM output before inserting into template                              |
|Event loop safety               |✅ All blocking handlers (texture, bucket, transcribe) use `run_in_executor` to avoid blocking the loop    |
|Thread safety — LLM config      |✅ `configure_llm()` uses double-checked locking (`threading.Lock`) — safe with `max_workers=3` executor   |
|System prompt — Claude compat   |✅ QA template uses `INSTRUCTIONS:` header, not `<<SYS>>`/`<</SYS>>` (Llama-2 tags that Claude ignores)   |
|Empty scrape guard              |✅ `run_pipeline` raises `RuntimeError` if scraper returns 0 comments — no silent garbage output           |
|Scraper failure classification  |✅ `ScrapeError(cause=...)` in `models.py` — auth_wall, proxy, selector_drift, rate_limit, timeout, unknown|
|Overflow handler — Phase 1c gap |✅ Telegram overflow sends truncated output as fallback; Citation UI link only if `CITATION_UI_BASE_URL` set|
|Whisper model caching           |✅ `_get_model()` caches loaded model in module-level dict — avoids 2-5s reload on every transcription     |
|Citation UI — `CITATION_UI_BASE_URL`|⚠️ Default `localhost:8000` won't work for external users. Must be set to LAN IP or tunnel URL on Mac Mini.|

-----

## 10. Next Steps

### Immediate (pre-build)

- [ ] Upload Bucket Holy Grail document via Claude Code session
- [ ] Confirm pre-emptive trailing line format for Buckets
- [ ] Set up project repo
- [ ] Set up Supabase project (output storage + citation index schema)
- [ ] Define and sign off Phase 1a go/no-go metrics and manual baseline sampling method

### Phase 1a — Scraping Spike

- [ ] Trial Approach 1: Playwright + stealth plugin on IG and FB
- [ ] Trial Approach 2: Brave headless via Playwright
- [ ] Trial Approach 3: Camoufox + Playwright
- [ ] Confirm PRAW for Reddit
- [ ] Evaluate: pick winner, document fallback
- [ ] Set up authenticated session management + residential proxy rotation
- [ ] Run 7-day soak test and publish pass/fail against Phase 1a go/no-go gate

### Phase 1b — Textures & Buckets

- [ ] Set up `python-telegram-bot` scaffold with user ID whitelist auth
- [ ] Install and configure LlamaIndex + `llama-index-llms-anthropic` + ChromaDB
- [ ] Build comment scraper → ChromaDB indexer (ephemeral per-run)
- [ ] Ingest Bucket Holy Grail into persistent ChromaDB index
- [ ] Implement shared pipeline: scrape → index → RAG → LLM → CitationBlock → Supabase → Telegram
- [ ] Implement mode switching: `/texture` vs `/bucket` prompt routing
- [ ] Implement post title logic (provided vs LLM-inferred)
- [ ] End-to-end test on real IG/FB/Reddit posts
- [ ] Validate output quality with ASOs/SOs
- [ ] Add Telegram overflow handling (chunking and/or fallback link to citation UI) so >4096 char outputs do not fail hard

### Phase 1c — Citation UI

- [ ] Define UI requirements with SOs/ASOs
- [ ] Confirm Supabase citation index schema is UI-ready (set in Phase 1b)
- [ ] Design side-by-side layout (Textures/Buckets output panel + source comment panel)
- [ ] Implement clickable [N] citation navigation
- [ ] Build against Supabase citation index from Phase 1b

## 11. Phase Exit Criteria (Definition of Done)

|Phase|Exit criteria|
|-----|-------------|
|**1a**|One scraping approach passes all go/no-go gate metrics in Section 7 and fallback path documented.|
|**1b**|Shared `/texture` and `/bucket` pipeline works end-to-end on IG/FB/Reddit, outputs are citation-grounded, and overflow handling prevents Telegram hard failure.|
|**1c**|Citation UI renders stored outputs with clickable `[N]` links to exact source comments and is usable by ASO/SO pilot users.|
|**1d**|`/transcribe` reliably returns DOCX for supported URLs with clear failure modes for unsupported/failed downloads.|
|**2**|At least one SO can run core workflows without ASO intervention using documented onboarding flow.|

### Phase 1d — Transcription

- [ ] Implement yt-dlp download + Whisper transcription
- [ ] Define chunking strategy for long videos
- [ ] Store transcript in Supabase, output DOCX to user
- [ ] Implement `/transcribe <url>` command

### Phase 2 — SO Self-Service

- [ ] Document SO-facing UX requirements
- [ ] Design SO onboarding flow
- [ ] Evaluate transcription engine alternatives (Deepgram, Whisper large-v3, etc.)
