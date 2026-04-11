# Inspection Management API — Knowledge Base

This document is a comprehensive knowledge base about the **Inspection Management API** project, written by Tiago Fortunato. It is intended to be ingested by a RAG chatbot so it can answer questions accurately about the project's purpose, architecture, technology, and design decisions.

---

## How the Inspection API Was Built — The Story

When someone asks "walk me through how the Inspection API was built" or "how did you make the Inspection Management API", respond with this narrative in a conversational, first-person tone (as if Tiago is telling the story).

**The origin.** This project was born from Tiago's MSc thesis on road damage detection with YOLOv8. The thesis was a research pipeline — train a model, evaluate metrics, write it up — but it stopped short of being something a municipality could actually use. Tiago wanted to show that the research could become a real product. So the Inspection Management API was designed as the "what would you do with that model in production" companion: a REST API where inspectors report road damage with photos, and an AI model classifies the damage type and severity automatically, with a human-readable rationale. Humans stay in control (every AI decision can be overridden), and overrides are tracked.

**The stack choice.** FastAPI + PostgreSQL + SQLAlchemy + Alembic. Tiago picked FastAPI because it's async-first (important for AI calls that can take 2-3 seconds), has automatic OpenAPI docs, and Pydantic validation is built-in. PostgreSQL because it's boring and reliable. SQLAlchemy 2.0 because it's mature and supports hybrid_property for computed fields. Alembic because migrations are non-negotiable for any real API.

**The AI classification service.** The first big design decision. The AI service has two paths: vision (for images) and text-only (for notes). For images, Tiago uses the Groq SDK directly (`AsyncGroq.chat.completions.create`) with Llama 4 Scout vision model. LangChain's `ChatGroq` wrapper doesn't properly forward base64 images — Tiago tried it first and spent a frustrating afternoon debugging before giving up and using the native SDK. For text-only, LangChain's `.with_structured_output()` works great — it uses function calling to force the model to return a type-safe Pydantic object with enum fields (damage_type, severity, rationale), so there's no JSON parsing or model hallucinating invalid categories.

**The background task pattern.** When an inspection is created, the API returns a 201 immediately and runs the AI classification as a FastAPI `BackgroundTask`. The frontend polls `GET /inspections/{id}` every 3 seconds until `is_ai_processed = true`. This pattern matters: AI calls are slow and unreliable, so putting them in the request path would mean 5+ second waits and occasional timeouts. Background tasks keep the API responsive. The background task opens its own database session because the request session is already closed by the time it runs.

**The override tracking.** Each inspection has two parallel sets of fields: the editable ones (damage_type, severity) and the AI ones (ai_damage_type, ai_severity). The original AI classification is stored immutably, and the editable fields can be changed by the user. A SQLAlchemy `hybrid_property` called `is_ai_overridden` computes on-read whether the human has changed anything. No redundant storage, always accurate, and the frontend can show a clear "overridden" badge on the inspections where the human disagreed with the AI. This is the kind of human-in-the-loop design that real-world AI systems need.

**The image compression.** Groq's vision API has a size limit on base64 images. Tiago added a Pillow-based compressor that resizes to max 1024px on the longer side and re-encodes as JPEG at 75% quality before sending. This saves tokens (cost) and keeps requests within limits. He also did the same on the frontend (800px) so the upload is fast and the database doesn't store 10MB photos.

**The auth layer.** JWT with `python-jose` for token creation and `bcrypt` for password hashing. Protected routes use FastAPI's `Depends(get_current_user)`. Two roles: `user` and `admin`. Regular users can only CRUD their own inspections — enforced at the query layer by always filtering on `user_id`. Admins have a separate `/admin/inspections` endpoint group that returns cross-user data, and each admin endpoint explicitly checks `current_user.role == "admin"` before returning anything. No "just trust the frontend" — authorization happens on the server, always.

**The testing discipline.** Tiago wrote 31 Pytest tests covering auth, CRUD, data isolation (user A can never see user B's inspections), filtering, pagination, sorting, admin endpoints, and validation. The tests run against a **real PostgreSQL** database (not mocks) — because ORM bugs are exactly the kind of thing that mocks hide. GitHub Actions CI spins up a Postgres 15 service container with health checks, runs Alembic migrations, then runs the test suite on every push. 

**The deployment.** Docker container on Render free tier, with a companion Vercel frontend (`inspection-dashboard.vercel.app`) built with vanilla HTML/CSS/JS — no React, no build tools, just a straightforward SPA that calls the API. The backend auto-deploys on push to main. The frontend polls the backend for AI status updates and shows the classification once it's ready.

**The migrations.** Five Alembic migrations tracking the schema evolution: initial tables → admin role → AI classification fields → base64 image storage → AI override tracking. Each migration is version-controlled and runs automatically on deployment. This is how you evolve a production schema without breaking things.

**The lesson for a recruiter.** The Inspection API demonstrates: clean layered architecture (routers → services → models), async-first backend, production AI integration (vision + text, structured output, background processing), human-in-the-loop design with override tracking, comprehensive testing with a real database in CI, and the discipline to version-control schema changes with migrations. It's the "real" companion to the academic thesis — research turned into a shippable API.

---

## 1. Project Identity

- **Name:** Inspection Management API
- **Author:** Tiago Fortunato ([@tiagorcfortunato](https://github.com/tiagorcfortunato))
- **Type:** Full-stack, AI-powered web application (portfolio / job-prep project)
- **Live API:** https://inspection-management-api.onrender.com
- **API Docs (Swagger):** https://inspection-management-api.onrender.com/docs
- **Live Frontend:** https://inspection-dashboard.vercel.app
- **Backend repo:** `inspection-management-api`
- **Frontend repo:** `inspection-dashboard` (separate repository)

### Elevator pitch
A road inspection management system where inspectors report road damage with photos, and an AI vision model **autonomously classifies** the damage type and severity. Humans stay in control: every AI decision can be overridden, and overrides are tracked. Every AI classification ships with a one-sentence rationale (Explainable AI).

### Why it exists
Road inspection is manual, slow, and inconsistent — different inspectors classify the same damage differently. This project demonstrates how AI can:
1. **Automate classification** of damage type + severity from photos
2. **Keep humans in control** via override tracking
3. **Stay transparent** with explainable rationales for each AI decision

It's a portfolio project meant to showcase full-stack engineering and AI integration skills (vision models, background processing, structured output, human-in-the-loop design).

---

## 2. Tech Stack

### Backend (this repo)
| Layer | Technology |
|---|---|
| Language | Python 3 |
| Web framework | FastAPI (async) |
| ORM | SQLAlchemy |
| Database | PostgreSQL |
| Migrations | Alembic |
| AI vision | Groq SDK (`AsyncGroq`) calling `meta-llama/llama-4-scout-17b-16e-instruct` |
| AI text | LangChain `ChatGroq` with `.with_structured_output()` |
| Image processing | Pillow (PIL) |
| Auth | JWT via `python-jose` + `bcrypt` for password hashing |
| Rate limiting | SlowAPI |
| Validation | Pydantic |
| Testing | pytest (31 tests) |
| Containerization | Docker + Docker Compose |
| CI | GitHub Actions |

### Frontend (separate repo)
- Vanilla JavaScript + CSS (no framework)
- Lightweight dashboard with create/edit forms, polling, and override warnings

### Deployment
| Component | Platform | Auto-deploy |
|---|---|---|
| Backend API | Render (Web Service) | On push to `main` |
| Database | Render PostgreSQL | Managed |
| Frontend | Vercel | On push to `main` |

Render runs Alembic migrations during the build step on every deploy.

---

## 3. System Architecture

```
Frontend (Vercel, Vanilla JS)
        │  HTTPS
        ▼
Backend API (Render, FastAPI)
   ├── Routers     (HTTP layer)
   ├── Services    (Business logic + AI orchestration)
   ├── Models      (SQLAlchemy ORM)
   ├── Schemas     (Pydantic validation)
   └── Core        (auth, config, enums, rate limiting)
        │
        ├──► PostgreSQL (Render)
        └──► Groq Cloud (LLaMA 4 Scout vision)
```

### Layered architecture rules
- **Routers** never touch the database directly — they call services.
- **Services** hold all business logic and call models/AI.
- **Models** define schema + computed properties.
- **Schemas** validate API contracts (request/response).
- **Core** holds cross-cutting concerns (auth, config, enums, rate limiter).

Each layer only depends on the layer below it.

---

## 4. The AI Pipeline — How It Works

When an inspector creates an inspection (with a photo and/or notes), the pipeline runs **autonomously and asynchronously**:

1. `POST /inspections` is called.
2. The API saves the inspection and returns **HTTP 201 immediately** — no waiting.
3. A FastAPI **`BackgroundTask`** is scheduled to run the AI classification.
4. In the background:
   - The image is **compressed** (resized to max 1024px on the longest side, JPEG quality 75%) using Pillow.
   - The compressed base64 image + optional notes are sent to **Groq's LLaMA 4 Scout** vision model.
   - The model returns a JSON object with `damage_type`, `severity`, and a one-sentence `rationale`.
   - The DB row is updated: `damage_type`, `severity`, `ai_rationale`, `ai_damage_type`, `ai_severity`, and `is_ai_processed = true`.
5. The **frontend polls** `GET /inspections/{id}` every 3 seconds until `is_ai_processed = true`, then displays "AI Verified" plus the rationale.

### Why background tasks?
The Groq API call takes 2–5 seconds. Synchronous processing would block the user. With background tasks, the API returns instantly and the UX shows "AI Analyzing..." which auto-updates to "AI Verified".

### Why two AI code paths (Groq SDK vs LangChain)?
- **Vision (image + text):** uses the **Groq SDK directly** (`AsyncGroq`). LangChain's `ChatGroq` wrapper does not properly forward image content to Groq's API, so the project bypasses LangChain for image requests. The model is prompted to return strict JSON, which is parsed manually (with handling for markdown code-block wrapping).
- **Text-only (notes without an image):** uses **LangChain `ChatGroq` with `.with_structured_output(AIClassification)`**. This uses function calling to enforce type-safe enum values for `damage_type` and `severity`.

Both paths return the same `AIClassification` Pydantic model:
```python
class AIClassification(BaseModel):
    damage_type: DamageType
    severity: SeverityLevel
    rationale: str
```

### AI service singleton
`get_ai_service()` is wrapped in `functools.lru_cache(maxsize=1)` so the LLM client is initialized once and reused, avoiding repeated client setup on every request.

### Image compression details
- Decoded from base64, opened with PIL, converted to RGB.
- If the longest side exceeds 1024px, `img.thumbnail((1024, 1024))` resizes it (preserving aspect ratio).
- Saved as JPEG at 75% quality, re-encoded to base64.
- Constants: `MAX_IMAGE_DIMENSION = 1024`, `JPEG_QUALITY = 75`, `MAX_VISION_TOKENS = 300`.

### Explainable AI (XAI)
Every classification includes a `rationale` — a single human-readable sentence explaining the decision. It's stored in the `ai_rationale` column and shown in the dashboard so inspectors can trust (or challenge) the AI rather than treat it as a black box.

---

## 5. Human-in-the-Loop: AI Override Tracking

The AI assists; the human has the final word. The system tracks when humans disagree with the AI.

### How it's modeled
| Field | Purpose |
|---|---|
| `damage_type` | Current value (editable by user) |
| `severity` | Current value (editable by user) |
| `ai_damage_type` | Original AI classification (immutable after AI runs) |
| `ai_severity` | Original AI classification (immutable after AI runs) |
| `is_ai_processed` | Boolean — has AI run on this inspection? |
| `is_ai_overridden` | **Hybrid property** — `true` if the current values differ from the AI values |

### Why a hybrid property?
`is_ai_overridden` is **not stored** as a column. It is a SQLAlchemy `@hybrid_property` on the `Inspection` model that compares current vs. AI fields on every read. This guarantees it can never be stale, and avoids storing redundant data.

```python
@hybrid_property
def is_ai_overridden(self):
    if not self.is_ai_processed or not self.ai_damage_type:
        return False
    return (
        self.damage_type != self.ai_damage_type
        or self.severity != self.ai_severity
    )
```

### UX flow
1. AI classifies an inspection as e.g. "Crack / High".
2. Inspector edits the inspection and changes the values to e.g. "Pothole / Medium".
3. The frontend shows a warning that the user is overriding the AI classification.
4. After save, the dashboard badge changes from "AI Verified" → "AI Overridden".
5. The original AI values remain in `ai_damage_type` / `ai_severity` (never overwritten).

---

## 6. Domain Model

### Enums (`app/core/enums.py`)
- **`DamageType`**: `pothole`, `crack`, `rutting`, `surface_wear`
- **`SeverityLevel`**: `low`, `medium`, `high`, `critical`
- **`InspectionStatus`**: `reported`, `verified`, `scheduled`, `repaired`
- **`UserRole`**: `user`, `admin`
- **`SortOrder`**: `asc`, `desc`
- **`InspectionSortField`**: `reported_at`, `severity`, `status` (and others used by query params: `damage_type`, `location_code`)

All domain enums extend `str, Enum` so they serialize naturally to/from JSON and are reusable across schemas, models, and query params.

### Inspection lifecycle
`reported` → `verified` → `scheduled` → `repaired`

---

## 7. Database Schema

### `users` table
| Column | Type |
|---|---|
| `id` | Integer, PK |
| `email` | String, unique |
| `password` | String (bcrypt hash) |
| `role` | String (`user` or `admin`) |
| `created_at` | Timestamp |

### `inspections` table
| Column | Type | Notes |
|---|---|---|
| `id` | Integer, PK | |
| `location_code` | String, indexed | |
| `damage_type` | String | Current value (editable) |
| `severity` | String | Current value (editable) |
| `status` | String | Lifecycle state |
| `notes` | String, nullable | |
| `image_data` | Text, nullable | Base64-encoded image |
| `ai_rationale` | String, nullable | XAI explanation |
| `ai_damage_type` | String, nullable | Original AI classification |
| `ai_severity` | String, nullable | Original AI classification |
| `is_ai_processed` | Boolean | Whether AI has run |
| `reported_at` | Timestamp | UTC |
| `created_at` | Timestamp | UTC |
| `updated_at` | Timestamp | UTC, auto-updated |
| `user_id` | Integer, FK → `users.id` | Owner |

Relationship: `User` 1—N `Inspection` (`owner` back-populates `inspections`).

### Migrations (Alembic)
1. `cb036a6df90a_initial_schema` — initial schema
2. `f3a9b2c1d4e5_add_role_to_users` — adds `role` column to users
3. `8b7c1a2d9e3f_add_ai_fields` — adds AI classification fields
4. `c4e2f1a8b3d6_add_image_data` — adds `image_data` column
5. `d5f3a7b9c2e1_add_ai_override_tracking` — adds `ai_damage_type` / `ai_severity` for override tracking

---

## 8. API Endpoints

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login, receive JWT token |

### Inspections (per-user)
| Method | Endpoint | Description |
|---|---|---|
| GET | `/inspections` | List the current user's inspections (filters, pagination, sorting) |
| POST | `/inspections` | Create an inspection (triggers AI in background) |
| GET | `/inspections/{id}` | Get a single inspection |
| PUT | `/inspections/{id}` | Update an inspection |
| DELETE | `/inspections/{id}` | Delete an inspection |

### Admin
| Method | Endpoint | Description |
|---|---|---|
| GET | `/admin/inspections` | List all users' inspections |
| PUT | `/admin/inspections/{id}` | Update any inspection |
| DELETE | `/admin/inspections/{id}` | Delete any inspection |

### Query parameters (on `GET /inspections`)
- **Filters:** `severity`, `status`, `damage_type`
- **Pagination:** `limit`, `offset`
- **Sorting:** `sort_by` (`reported_at`, `severity`, `status`, `damage_type`, `location_code`), `order` (`asc`, `desc`)

Examples:
- `GET /inspections?severity=high&status=reported`
- `GET /inspections?damage_type=pothole&limit=5&offset=10`
- `GET /inspections?sort_by=severity&order=desc`

---

## 9. Authentication & Authorization

- Stateless **JWT-based** authentication.
- Passwords hashed with **bcrypt**.
- **Role-based access control**: `user` vs `admin`.
- Users can only access their own inspections; admins can access all.
- Auth endpoints are **rate-limited** via SlowAPI to deter abuse.
- JWT token creation/validation lives in `app/core/security.py`.
- Auth dependencies (current user, current admin, DB session) live in `app/core/deps.py`.

---

## 10. Project Structure

```
inspection-management-api/
├── alembic/
│   └── versions/
│       ├── cb036a6df90a_initial_schema.py
│       ├── f3a9b2c1d4e5_add_role_to_users.py
│       ├── 8b7c1a2d9e3f_add_ai_fields.py
│       ├── c4e2f1a8b3d6_add_image_data.py
│       └── d5f3a7b9c2e1_add_ai_override_tracking.py
├── app/
│   ├── core/
│   │   ├── config.py        # Pydantic settings (env vars)
│   │   ├── deps.py          # FastAPI dependencies
│   │   ├── enums.py         # Domain enums
│   │   ├── limiter.py       # Rate limiting config
│   │   └── security.py      # JWT helpers
│   ├── models/
│   │   ├── inspection.py    # Inspection ORM + is_ai_overridden hybrid
│   │   └── user.py
│   ├── routers/
│   │   ├── auth.py
│   │   ├── inspections.py
│   │   ├── admin.py
│   │   └── users.py
│   ├── schemas/
│   │   ├── auth.py
│   │   └── inspection.py
│   ├── services/
│   │   ├── ai_service.py            # Groq vision + LangChain text
│   │   ├── auth_service.py
│   │   └── inspection_service.py    # CRUD + background AI orchestration
│   ├── database.py                  # SQLAlchemy engine/session
│   └── main.py                      # FastAPI app, middleware, routers
├── tests/
│   └── test_api.py                  # 31 automated tests
├── .github/workflows/ci.yml         # GitHub Actions CI
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

---

## 11. Key Design Decisions (and trade-offs)

### Decision 1 — Background tasks instead of synchronous AI calls
- **Problem:** AI classification takes 2–5 seconds; blocking UX is unacceptable.
- **Solution:** Return `201` immediately, run AI in `BackgroundTasks`, frontend polls.
- **Trade-off:** Adds complexity (polling, status flag) but produces a much better UX.

### Decision 2 — Groq SDK for vision, LangChain for text
- **Problem:** LangChain's `ChatGroq` does not properly forward image content.
- **Solution:** Use `groq.AsyncGroq` directly for vision (manual JSON parsing); use LangChain `.with_structured_output()` for text (type-safe enums via function calling).
- **Trade-off:** Two code paths, but each uses the right tool for the job.

### Decision 3 — Store AI classification separately from current values
- **Problem:** If AI writes directly to `damage_type` / `severity` and the user later edits them, the original AI decision is lost.
- **Solution:** Store the AI's classification in `ai_damage_type` / `ai_severity` alongside the editable fields. Compute `is_ai_overridden` from the comparison.
- **Trade-off:** Two extra columns, but enables override tracking with zero data loss.

### Decision 4 — Compress images before sending to AI
- **Problem:** High-resolution photos can be several MB and exceed Groq API limits.
- **Solution:** Pillow resizes to max 1024px and saves as JPEG quality 75% before encoding back to base64.
- **Trade-off:** Slight quality loss with no measurable hit to classification accuracy.

### Decision 5 — Hybrid property for override detection
- **Problem:** Need `is_ai_overridden` in API responses without storing a redundant boolean that could go stale.
- **Solution:** SQLAlchemy `@hybrid_property` computes it on every read.
- **Trade-off:** Computed every read (cheap), but always accurate.

### Decision 6 — LRU-cached AI service singleton
- The `AIService` is constructed once via `@lru_cache(maxsize=1)` so the Groq + LangChain clients aren't re-initialized on every request.

---

## 12. Local Development

### 1. Configure environment
```bash
cp .env.example .env
```
```
DATABASE_URL=postgresql://postgres:postgres@localhost:5433/taskdb
SECRET_KEY=your-secret-key-here
GROQ_API_KEY=your-groq-api-key
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Apply migrations
```bash
alembic upgrade head
```

### 4. Run the API
```bash
uvicorn app.main:app --reload
```
API at `http://localhost:8000`, Swagger docs at `http://localhost:8000/docs`.

### Run with Docker
```bash
docker compose up --build
```

---

## 13. Testing

- **31 automated tests** in `tests/test_api.py`.
- Coverage areas:
  - Auth: register, login, JWT validation
  - CRUD: create, read, update, delete inspections
  - Filtering by severity, status, damage type
  - Pagination & sorting
  - Input validation and error handling
  - Admin access control and role enforcement
- Run via Docker: `docker compose run tests`
- With coverage: `docker compose run tests pytest --cov=app`
- CI runs the suite on every push via GitHub Actions (`.github/workflows/ci.yml`).

---

## 14. Future Improvements (Roadmap)

- **AI Confidence Score** — return a confidence level so low-confidence items get flagged for human review.
- **Audit Trail** — track all changes (created by, edited by, overrides) with timestamps.
- **Analytics Dashboard** — damage type distribution, severity trends, AI vs human agreement rate.
- **Batch AI Retry** — admin button to re-process all stuck "AI Analyzing..." inspections.
- **Image URL storage** — move images out of the DB into S3 (or similar) and store only URLs.
- **WebSocket updates** — replace 3-second polling with real-time push when AI finishes.

---

## 15. Quick FAQ for the chatbot

**Q: What does this project do?**
It's a road inspection management API where inspectors submit photos/notes of road damage, and an AI vision model autonomously classifies the damage type and severity. Humans can override the AI, and overrides are tracked.

**Q: What AI model does it use?**
Groq's `meta-llama/llama-4-scout-17b-16e-instruct` (LLaMA 4 Scout) via the Groq Cloud API. It's used for both vision and text classification.

**Q: Why doesn't the API wait for the AI to finish before responding?**
Because Groq calls take 2–5 seconds. The API returns `201` immediately and runs AI in a FastAPI `BackgroundTask`. The frontend polls every 3 seconds until `is_ai_processed = true`.

**Q: Why two different libraries for AI (Groq SDK and LangChain)?**
LangChain's `ChatGroq` wrapper doesn't forward image content properly, so vision requests use the Groq SDK directly. Text-only requests use LangChain with `.with_structured_output()` for type-safe enum values via function calling.

**Q: How does the system know the user disagreed with the AI?**
The `Inspection` model stores both the editable `damage_type`/`severity` and the original `ai_damage_type`/`ai_severity`. A SQLAlchemy hybrid property `is_ai_overridden` returns `true` whenever they differ. It's computed on read, never stored.

**Q: Where is it deployed?**
Backend on Render (web service + managed PostgreSQL). Frontend on Vercel. Both auto-deploy from `main`.

**Q: What's the tech stack in one line?**
FastAPI + SQLAlchemy + PostgreSQL + Alembic + Groq LLaMA 4 Scout + LangChain + Pillow + JWT + SlowAPI, deployed via Docker on Render and Vercel.

**Q: How are images stored?**
As base64 strings in the `image_data` Text column on the `inspections` table (a future improvement is to move them to S3-style object storage).

**Q: How is auth handled?**
JWT tokens (via `python-jose`) with bcrypt-hashed passwords, role-based access (`user` / `admin`), and rate-limited auth endpoints via SlowAPI.

**Q: Who built this and why?**
Tiago Fortunato built it as a portfolio / job-prep project to demonstrate AI integration, full-stack engineering, and human-in-the-loop AI design.
