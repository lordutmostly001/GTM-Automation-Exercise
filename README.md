# 🚀 TechSparks 2024 — AI-Powered GTM Automation System

An end-to-end AI-powered Go-To-Market automation pipeline that transforms a raw TechSparks attendee/speaker list into enriched contacts, AI-generated personas, context-aware personalization, routed lead ownership, and multi-phase outreach automation.

**Built with:** Python · n8n (free tier) · Google Sheets · OpenRouter (Claude) · Apollo API (free tier)

---

## 🧠 Architecture Overview

```
Scraper → Master Sheet → Enrichment → Persona AI → Routing → Outreach Engine
```

| Layer | Purpose | Tool |
|---|---|---|
| Data Collection | Scrape TechSparks contacts | Python + Selenium |
| Enrichment | LinkedIn, email, company size, funding | Apollo API |
| AI Context | Persona + personalization themes | Claude via OpenRouter |
| Lead Routing | SDR/AE/Leadership assignment | n8n logic |
| Outreach | Multi-phase ABM automation | n8n + Google Sheets |


---

## 1️⃣ Data Collection

**File:** `techsparks_scraper.py`

Scrapes TechSparks 2024 speakers using Selenium and BeautifulSoup.

**Outputs:**
- `techsparks_speakers_raw.csv`
- `techsparks_contacts_200.csv` (scraped + mock expansion to 200 rows)

**Setup & Run:**

```bash
pip install selenium beautifulsoup4 pandas requests webdriver-manager
python techsparks_scraper.py
```

> If scraping fails, the system automatically falls back to a predefined speaker dataset.

---

## 2️⃣ Data Enrichment (Apollo Workflow)

Reads unenriched contacts from Google Sheets, calls the Apollo People Search API, and writes enriched data back to the sheet.

**Extracted fields:**
- LinkedIn URL
- Email
- Company size band
- Funding stage

**Recalculated fields:**
- Seniority tier
- Industry vertical
- ICP score (1–5)

**Smart logic:**
- Email reveal only for ICP ≥ 4
- Batch control & rate limiting
- Name matching heuristics
- Industry keyword inference

---

## 3️⃣ AI Persona & Context Generation

**n8n workflow:** `Persona_generation.json` — powered by Claude (via OpenRouter)

Filters enriched contacts, builds structured prompts, and generates persona data in strict JSON format.

**Outputs per contact:**

| Field | Description |
|---|---|
| `persona_summary` | AI-generated persona description |
| `context_hook` | Personalized conversation opener |
| `personalization_themes` | Key themes for outreach |
| `confidence_flag` | HIGH / MEDIUM / LOW |

**Guardrails:**
- JSON-only responses enforced
- No hallucinated facts
- Disallowed generic phrases list
- Minimum word thresholds
- Confidence downgraded for generic language, missing fields, short responses, or government contacts

---

## 4️⃣ Lead Routing Logic

**n8n workflow:** `lead_routing.json`

**Routing rules:**

| Seniority | Owner Role | Sender Level |
|---|---|---|
| C-Suite | Senior AE | Leadership |
| VP/Director | AE | AE |
| Manager/IC | SDR | SDR |

**Additional logic:**
- ICP 5 + C-Suite → Leadership review required
- Round-robin assignment
- Company-level conflict detection
- Deduplication by normalized company key

---

## 5️⃣ Outreach Engine

**n8n workflow:** `outreach.json`

**Multi-phase ABM sequence:**

| Phase | Channel |
|---|---|
| Pre-event | LinkedIn Connect |
| During event | LinkedIn DM |
| Post-event | Email |
| Follow-up 1 | Email |

**Controls:**
- Event-date-driven phase logic
- Hard stop at D+21
- Daily send cap
- ICP threshold filtering
- Leadership review gating
- Blocked contact exclusion

**Personalization varies by:**
- Industry (VC vs. Operator)
- Seniority (C-Suite vs. Manager)
- AI-generated themes and context hook injection

---

## ⚙️ Environment Variables

```env
GSHEET_DOC_ID=
APOLLO_API_KEY=
OPENROUTER_API_KEY=
MAX_SENDS_PER_RUN=
```

---

## 📊 Google Sheet Schema

The master sheet serves as database, state machine, audit log, and retry controller. It stores:

- Raw fields (name, company, title)
- Enrichment fields
- AI persona fields
- Routing fields
- Outreach state
- Confidence & validation notes


---

## 🛡️ Safeguards & Failure Handling

| Scenario | Handling |
|---|---|
| LinkedIn profile not found | `enrichment_status = not_found` |
| Generic AI output | `confidence_flag = LOW` → blocked from outreach |
| Duplicate contacts | Company conflict detection + normalized root matching |

**Scaling to 2,000+ contacts** is supported via batch control, rate limiting, horizontal workflow cloning, and queue-based sheet partitions.

---

## 🚧 Out of Scope (Intentional)

| Area | Reason |
|---|---|
| Real email sending | Avoid spam / domain reputation risk |
| LinkedIn auto-send | Compliance + platform risk |
| Email verification API | Free-tier constraint |
| CRM sync | Scope limit |

---

## 📈 Key Metrics Optimized

- Email deliverability
- LinkedIn acceptance rate
- Personalization specificity
- Senior-lead engagement rate

---

## 🧩 Tech Stack & Rationale

| Tool | Why |
|---|---|
| Python | Scraping + pipeline control |
| Selenium | JS-rendered site support |
| n8n | Visual automation + conditional logic |
| Google Sheets | State engine + shared storage |
| OpenRouter | Free/low-cost LLM API access |
| Claude Haiku | Cost-efficient persona generation |
| Apollo API | Structured contact enrichment |
