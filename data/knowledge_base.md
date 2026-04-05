# Tiago Fortunato — Technical Knowledge Base

> This document is the authoritative source of truth for Tiago Fortunato's professional profile. It is used by the RAG chatbot to answer recruiter questions with accurate, technical depth.

---

## About Tiago

Tiago Fortunato is a **Full-Stack Developer and Founder** based in **Berlin, Germany**. He is currently completing an **MSc in Software Engineering** at the University of Europe for Applied Sciences (graduating 2026), with a background in Mechanical Engineering (BSc, UERJ, Brazil).

He is the **sole founder and developer of Odys** (odys.com.br) — a live, production WhatsApp-first scheduling SaaS for freelance professionals in Brazil, built entirely from architecture to deployment.

His technical focus spans **AI application engineering** (RAG pipelines, computer vision, ML), **backend API development** (Python/FastAPI), and **full-stack SaaS product development** (Next.js/TypeScript/Supabase).

**Contact:**
- Email: tifortunato.eng@gmail.com
- Phone: +49 172 238 9909
- Portfolio: tiagorcfortunato.vercel.app
- GitHub: github.com/tiagorcfortunato
- LinkedIn: linkedin.com/in/tiagorcfortunato

**Languages:** Portuguese (native), English (fluent), German (B2.2, actively improving)

**Available for:** Full-Stack or Backend Developer roles in Berlin or remote.

---

## Academic Excellence

### MSc Thesis — Expert System for Road Surface Hazard Detection

**Full Title:** *Expert System for Road Surface Hazard Detection: A Deep Learning-Based Detection and Maintenance Prioritization Pipeline*

**Institution:** University of Europe for Applied Sciences, Berlin
**Submitted:** 15 February 2026
**Supervisors:** Prof. Dr. Raja Hashim (first), Prof. Dr. Shan Faiz (second)

#### Problem Statement

Traditional road inspection is manual, costly, slow, and subjectively inconsistent. Existing deep-learning approaches for road damage detection focus solely on maximizing detection accuracy on benchmark datasets — they treat damage detection as an isolated perception task without addressing how detected defects should be **prioritized for maintenance planning**. This gap between visual inspection and actionable infrastructure management decisions was the central motivation for the thesis.

#### Proposed Solution — Hybrid Pipeline

Tiago designed a **modular two-component pipeline** that separates perception from reasoning:

1. **Detection Component (YOLOv8):** A YOLO-based object detection model identifies and localizes road surface defects from monocular RGB images under real-world, unconstrained environmental conditions.

2. **Expert System (Rule-Based Prioritization):** A deterministic, rule-based decision-support system processes the structured detection outputs (bounding boxes, class labels, confidence scores) and assigns maintenance priority levels (Low / Medium / High) based on:
   - Defect type (e.g., pothole, longitudinal crack, transverse crack, alligator crack)
   - Detection confidence score (configurable thresholds)
   - Number of detections per image (aggregation)
   - Contextual operational criteria

The interface between both components is: `P = f(D)`, where `f(·)` is the non-probabilistic rule function and `D` is the structured detector output. This separation allows decision logic to be modified without retraining the perception model.

#### Dataset

**RDD2022** (Road Damage Dataset 2022) — a large-scale benchmark containing annotated road images from multiple countries with varied lighting, weather, and surface conditions. Key challenge: class imbalance and small-defect detection.

#### Experimental Design (EXP1–EXP4)

Controlled experiments varying one factor at a time:

| Experiment | Model | Main Modification |
|---|---|---|
| EXP1 | YOLOv8n | Baseline configuration |
| EXP2 | YOLOv8n | Training epochs: 50 → 100 |
| EXP3 | YOLOv8n | Image size: 640 → 800 |
| EXP4 | YOLOv8s | Higher-capacity model (best config) |

#### Results

**Best configuration (EXP4 — YOLOv8s):**
- **mAP50: 0.663**
- **Precision: 0.694**
- **Recall: 0.604**
- Post-processing (quantile-based prioritization + deterministic filtering) **reduced noisy detections by 31.2%**
- Every prioritization decision is traceable to explicit rules — no black-box decisions

#### Key Technical Contributions

- Demonstrated that combining deep learning with explicit rule-based reasoning improves both performance and **operational interpretability**
- Modular architecture allows independent testing of perception and decision-making components
- Reproducible benchmarking: fixed random seeds, pinned library versions, held-out test set never touched during training
- Post-processing aggregation stabilizes prioritization across confidence threshold variations

#### Tech Stack (Thesis)

Python, PyTorch, YOLOv8 (Ultralytics), Scikit-learn, Pandas, Linux, GPU-accelerated training

---

## Full-Stack & AI Projects

### 1. RAG PDF Chatbot (2026)

**Repository:** github.com/tiagorcfortunato/rag-pdf-chatbot
**Live Demo:** rag-pdf-chatbot-0w9z.onrender.com

A production-ready Retrieval-Augmented Generation (RAG) application that allows users to upload PDFs and conduct a contextual conversation with the content — with full conversation history and source attribution (section + page number).

#### Architecture

```
PDF Upload
    ↓
PyMuPDF (fitz) font-size analysis → heading detection → section-aware chunks
    ↓
fastembed (BAAI/bge-small-en-v1.5) — local embeddings, ~80MB model
    ↓
ChromaDB (persistent vector store)

──────────────────────────────────────

User question
    ↓
History-enriched search query (last 2 exchanges prepended)
    ↓
Similarity search → top-6 most relevant chunks
    ↓
LangChain prompt: system instructions + conversation history + context + question
    ↓
Groq LLM (Llama 3.1 8B Instant)
    ↓
Answer + source attribution (section + page)
```

#### Key Technical Details

- **Section-aware chunking:** Uses PyMuPDF to extract font sizes across all spans. Computes median font size, then flags any text 15%+ larger as a heading. Splits document along headings — keeps small sections whole, uses `RecursiveCharacterTextSplitter` only for large sections. Each sub-chunk is prefixed with its section title for retrieval coherence.
- **History-enriched retrieval:** Enriches search queries with the last 2 conversation exchanges, enabling natural follow-up questions ("tell me more about the first one").
- **Source attribution:** Every answer returns the exact section name and page number of the retrieved chunks.
- **Multi-document support:** Users can query individual documents by `document_id` or query all uploaded documents simultaneously.
- **Recruiter persona system prompt:** Configured as a Professional Talent Assistant for Tiago, instructing the LLM to answer strictly from context, never hallucinate, and highlight technical skills when information is missing.
- **REST API:** Full OpenAPI/Swagger docs at `/docs`.

#### Tech Stack

| Layer | Technology |
|---|---|
| Backend | FastAPI |
| PDF Parsing | PyMuPDF (fitz) |
| Embeddings | BAAI/bge-small-en-v1.5 via fastembed (local) |
| Vector DB | ChromaDB (persistent) |
| LLM | Llama 3.1 8B via Groq API |
| Orchestration | LangChain |
| Frontend | Vanilla HTML/CSS/JS (served by FastAPI) |
| Deployment | Docker, Docker Compose, Render |
| Testing | Pytest + GitHub Actions CI/CD |

#### Challenges and Solutions

- **Challenge:** Generic chunking loses section context, causing poor retrieval.
  **Solution:** Built custom font-size-based heading detection with PyMuPDF — no external dependencies, works on any PDF.

- **Challenge:** Follow-up questions fail vector search when they lack explicit keywords.
  **Solution:** History-enriched query construction prepends recent conversation context before embedding the search query.

- **Challenge:** Free embedding APIs add latency and cost at scale.
  **Solution:** Runs `BAAI/bge-small-en-v1.5` locally via fastembed — downloaded once (~80MB), zero API cost.

---

### 2. Inspection Management API (2026)

**Repository:** github.com/tiagorcfortunato/inspection-management-api
**Live API:** inspection-management-api.onrender.com
**Live Dashboard:** inspection-dashboard.vercel.app
**API Docs:** inspection-management-api.onrender.com/docs

A production-oriented REST API for infrastructure inspection management, demonstrating clean backend architecture with full test coverage and CI/CD.

#### Features

- **JWT Authentication:** User registration, login, protected routes via dependency injection
- **Per-user data isolation:** Each user only accesses their own inspection records
- **Status lifecycle:** `reported` → `verified` → `scheduled` → `repaired`
- **Filtering:** By `severity`, `status`, `damage_type`
- **Pagination:** `limit` + `offset` query parameters
- **Sorting:** By `reported_at`, `severity`, or `status` (asc/desc)

#### API Endpoints

```
POST /auth/register
POST /auth/login

GET    /inspections
POST   /inspections
GET    /inspections/{inspection_id}
PUT    /inspections/{inspection_id}
DELETE /inspections/{inspection_id}
```

#### Architecture (Layered)

| Layer | Responsibility |
|---|---|
| Routers | Handle HTTP requests and responses |
| Services | Business logic |
| Models | Database entities (SQLAlchemy) |
| Schemas | Request/response validation (Pydantic) |
| Core | Auth, dependencies, enums |

#### Testing & CI/CD

- **31 Pytest tests** covering: auth flows, CRUD operations, filtering, pagination, sorting, validation edge cases, admin access control
- **GitHub Actions CI:** tests run automatically on every push
- **Docker Compose:** isolated test environment (`docker compose run tests`)

#### Tech Stack

Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic (migrations), Pydantic, JWT (python-jose), Pytest, Docker, Docker Compose, GitHub Actions, Render

---

### 3. Odys — Scheduling SaaS for Freelance Professionals (2026–present)

**Live Product:** odys.com.br

A WhatsApp-first SaaS platform built entirely solo — from architecture to production — targeting Brazilian freelance professionals (psychologists, personal trainers, beauty professionals, etc.) who manage appointments manually via WhatsApp.

#### Problem It Solves

Brazilian freelance professionals lose time and revenue managing bookings manually via WhatsApp: confirming appointments one by one, tracking payments in spreadsheets, and experiencing frequent no-shows due to lack of automated reminders. Existing tools are too complex or lack real WhatsApp integration.

#### Key Features

**For professionals:**
- Public booking page at `/p/[slug]` with real-time availability calendar
- Dashboard with daily agenda and upcoming appointments
- Confirm, reject, and cancel bookings
- Automatic WhatsApp reminders sent 24h before appointments
- Payment tracking per session
- Configurable availability and payment policies
- Guided onboarding
- Real-time notifications

**For clients:**
- Self-service booking via the professional's public page
- Client area with appointment history (`/meus-agendamentos`)
- WhatsApp confirmation and reminders

#### Technical Architecture

**Multi-tenant architecture:** Each professional gets an isolated public booking page at `/p/[slug]`. Data is fully isolated per tenant.

**WhatsApp-native reminders:** Self-hosted **Evolution API v2** running on Railway (Docker image: `tiagorcfortunato/evolution-api-odys`). Reminders are triggered by **Supabase pg_cron** — a PostgreSQL-native cron job that periodically calls `/api/cron/reminders`, which queries upcoming appointments and sends WhatsApp messages via Evolution API. This is NOT a third-party bot — the message appears from the professional's own WhatsApp number.

**Payments:** Stripe subscriptions + PIX with webhook handling. Resolved PgBouncer transaction mode compatibility issue with Drizzle ORM (required `pgbouncer=true&connection_limit=1` in connection string).

**Rate limiting:** Upstash Redis with `@upstash/ratelimit` on API routes.

**Error monitoring:** Sentry (edge + server configs).

**Transactional email:** Resend for booking confirmations and notifications.

#### Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router) + TypeScript |
| Styling | Tailwind CSS v4 + shadcn/ui |
| Database | Supabase (PostgreSQL) |
| ORM | Drizzle ORM |
| Auth | Supabase Auth (email/password) |
| WhatsApp | Evolution API v2 (self-hosted, Railway) |
| Payments | Stripe (subscriptions + PIX) |
| Email | Resend |
| Rate limiting | Upstash Redis |
| Monitoring | Sentry |
| Scheduled tasks | Supabase pg_cron |
| App deployment | Vercel |
| WhatsApp API deployment | Railway |

#### Challenges and Solutions

- **Challenge:** PgBouncer transaction mode breaks Drizzle ORM's connection pooling.
  **Solution:** Added `pgbouncer=true&connection_limit=1` to the DATABASE_URL — resolved without switching away from PgBouncer.

- **Challenge:** WhatsApp reminders must come from the professional's own number (not a generic bot).
  **Solution:** Self-hosted Evolution API v2 on Railway; the professional scans a QR code once to connect their number; reminders are then sent natively.

- **Challenge:** Cron jobs in serverless environments are unreliable.
  **Solution:** Used Supabase `pg_cron` (PostgreSQL-native) which runs inside the database layer — independent of the Next.js serverless functions.

---

## Core Skills

### Backend Engineering
- **Python** — primary language; production-grade codebases
- **FastAPI** — REST APIs, dependency injection, Pydantic validation, OpenAPI docs
- **PostgreSQL** — schema design, migrations (Alembic, Drizzle), query optimization
- **SQLAlchemy** — ORM, session management, relationships
- **Drizzle ORM** — TypeScript-native ORM on PostgreSQL/Supabase
- **Pydantic** — data validation and settings management
- **Alembic** — database migration management
- **JWT** — auth flows, token-based security
- **Pytest** — unit and integration testing, fixtures, coverage

### AI & Machine Learning
- **RAG (Retrieval-Augmented Generation)** — end-to-end pipeline design and implementation
- **LangChain** — orchestration, prompt templates, message history, chains
- **ChromaDB** — vector store, persistent embeddings, metadata filtering
- **Vector Search** — embedding-based similarity retrieval, query enrichment strategies
- **fastembed** — local embedding model inference (BAAI/bge-small-en-v1.5)
- **Groq API** — LLM inference (Llama 3.1 8B)
- **YOLOv8 (Ultralytics)** — object detection, training, evaluation (mAP, precision, recall)
- **PyTorch** — model training, GPU-accelerated inference
- **Scikit-learn** — classical ML, evaluation metrics
- **Pandas** — data manipulation and analysis
- **PyMuPDF (fitz)** — PDF parsing, font-size-based document analysis
- **Claude Code** — AI-assisted development workflow

### Full-Stack & SaaS
- **TypeScript** — type-safe full-stack development
- **Next.js 16** (App Router) — SSR, API routes, dynamic routing, server components
- **Supabase** — PostgreSQL-as-a-service, Auth, pg_cron, real-time
- **Stripe** — subscription billing, PIX payments, webhook handling
- **Resend** — transactional email
- **Upstash Redis** — serverless rate limiting
- **Evolution API v2** — self-hosted WhatsApp messaging integration
- **Tailwind CSS + shadcn/ui** — component-based UI development

### DevOps & Infrastructure
- **Docker** — containerization, multi-service Docker Compose setups
- **GitHub Actions** — CI/CD pipelines, automated test runs
- **Vercel** — Next.js deployments, environment management
- **Railway** — Docker-based service deployments (Evolution API)
- **Render** — FastAPI/Python service deployments
- **Git** — version control, branching strategies

### Methodologies & Practices
- Clean layered architecture (Routers → Services → Models → Schemas)
- Test-driven development with automated CI
- Multi-tenant SaaS architecture
- Modular ML pipeline design (perception/reasoning separation)
- Production monitoring and error tracking (Sentry)
- Reproducible ML experiments (fixed seeds, controlled ablations, held-out test sets)

---

## Professional Experience

### Odys — Founder & Full-Stack Developer (2026–present, Berlin)
Built and launched a live SaaS product from zero — market research, product design, technical architecture, implementation, and production deployment — as sole developer.

### Fortunato Joias — Project Manager (2019–2024, Brazil)
End-to-end ownership of production planning, supplier relationships, and delivery cycles for a jewelry manufacturing business. Five years of operational management.

### Metalúrgica Besser — Engineering Intern, Logistics & Operations (2018–2019, Rio de Janeiro)
Supported logistics routines and production planning; reduced delays through structured problem solving.

### Guide Idiomas — Co-Founder & German Teacher (2016–2018, Rio de Janeiro)
Co-founded a German language school; developed structured curricula and managed operations.

---

## Education

| Degree | Institution | Location | Year |
|---|---|---|---|
| MSc Software Engineering | University of Europe for Applied Sciences | Berlin, Germany | 2024–2026 |
| Exchange — Mechanical Engineering | Hochschule Wismar | Germany | 2014–2016 |
| BSc Mechanical Engineering | UERJ | Rio de Janeiro, Brazil | 2013–2018 |

**MSc Thesis:** *Expert System for Road Surface Hazard Detection* — YOLOv8 pipeline with rule-based maintenance prioritization (RDD2022 dataset)
