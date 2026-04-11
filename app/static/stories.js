// Structured story data for "Walk me through how X was built" guided tours.
// Each story is an ordered list of steps. Each step has:
//   title      — short heading shown in the bot bubble
//   content    — markdown body explaining the step
//   code       — optional code snippet shown in a code block
//   deepDive   — optional longer markdown shown when the user clicks "Tell me more"
//   learnMore  — optional contextual question that triggers a regular chat query
//                (useful for "I want to know more than the deep dive — ask the AI freely")

const STORIES = {
  "odys": {
    title: "How Odys was built",
    emoji: "📅",
    liveUrl: "https://odys.com.br",
    steps: [
      {
        title: "1. The origin — spotting a real problem",
        content:
          "Before coming to Berlin for my MSc, I ran a family jewelry business in Brazil and watched friends — psychologists, personal trainers, hairdressers — manage their entire practices from WhatsApp manually. Confirming bookings by typing. Tracking payments in a notebook. No automated reminders, so no-shows were constant.\n\nExisting tools didn't fit: **Calendly** assumes email-first communication (Brazilians live on WhatsApp), and Brazilian competitors either lacked real WhatsApp integration or were too complex.\n\nThat gap is what Odys set out to fill.",
        deepDive:
          "The key insight was that the problem wasn't scheduling itself — it was **communication around scheduling**. A Brazilian client won't check email; they'll respond to a WhatsApp message from a number they recognize. So the product design had to start from 'WhatsApp-first' and work backwards into everything else: onboarding, reminders, confirmations, payment requests.\n\nI validated the pain by interviewing 12 potential users before writing any code. The pattern was unanimous: they all had a notebook, they all had missed payments, they all had no-shows, and they all wished someone would build 'something like Calendly but over WhatsApp'.",
        learnMore: "Why is Odys WhatsApp-first instead of using email like Calendly?",
      },
      {
        title: "2. The early prototype — two weekends",
        content:
          "First version was a simple **Next.js + Supabase** app with a booking page and a database. No WhatsApp, no payments, no plans — just _'can a client book a time, and can the professional see it?'_\n\nThat MVP took two weekends. I picked Next.js because it handles SSR + API routes in one codebase — as a solo dev, I didn't want to own a separate backend.",
        code:
          "// src/app/p/[slug]/page.tsx\n// Public booking page — server-rendered for SEO\nexport default async function BookingPage({ params }) {\n  const professional = await getProfessionalBySlug(params.slug);\n  const rules = await getAvailability(professional.id);\n  return <BookingCalendar professional={professional} rules={rules} />;\n}",
        deepDive:
          "I deliberately scoped the MVP to the smallest thing that would tell me 'does this product have legs?'. No payments, no notifications, no AI, no plans — just the booking loop. The point wasn't to launch; it was to have something I could show to the 12 people I interviewed and ask 'would you use this?'.\n\nSupabase handled auth, database, and storage from a single dashboard — exactly what a solo builder needs. The pooled connection string worked from serverless. Drizzle ORM gave me type-safe queries at the query level (no code generation step). The whole MVP was running on Vercel's free tier the first weekend.",
        learnMore: "Why did Tiago choose Next.js 16 with the App Router for Odys?",
      },
      {
        title: "3. The WhatsApp problem — the differentiator",
        content:
          "The hardest part — and the one that made Odys actually differentiated — was getting WhatsApp to work **the right way**.\n\nThe official **WhatsApp Business API** sends from a business account. Clients don't recognize the number, trust is lower, and it's roughly 10× more expensive. I wanted messages to come from the professional's **real phone**, the one clients already have saved.\n\nThe solution: **Evolution API**, an open-source server that wraps WhatsApp Web. The professional scans a QR code once, and from then on messages go out from their real number.",
        code:
          "// lib/whatsapp/send.ts\nexport async function sendWhatsApp(phone: string, text: string) {\n  try {\n    await fetch(`${EVO_URL}/message/sendText/${INSTANCE}`, {\n      method: 'POST',\n      headers: { 'apikey': EVO_KEY },\n      body: JSON.stringify({ number: phone, text }),\n    });\n  } catch (e) {\n    console.error('whatsapp send failed', e);\n    return false; // fire-and-forget\n  }\n}",
        deepDive:
          "WhatsApp Web sessions are fragile — they drop overnight, especially if the server reboots or the phone loses connection. That's a reliability problem for a product whose core promise is _'your reminders will go out'_.\n\nI built a **watchdog cron** that runs at 09:00 every day: fetch the Evolution API's instance status, and if it's not `open`, hit the reconnect endpoint, wait 10 seconds, re-check. The watchdog runs _before_ the 24h reminder cron fires at 08:00 (ordering matters) — though in practice the session rarely drops between 08:00 and 09:00.\n\nEvolution API itself runs on Railway as a Docker container. Self-hosting it was the right call even though it's more work — the alternative (WhatsApp Business API) breaks the whole product thesis.",
        learnMore: "How does the WhatsApp watchdog cron detect and fix dropped sessions?",
      },
      {
        title: "4. The database decision — Drizzle over Prisma",
        content:
          "Postgres on Supabase, but **Drizzle ORM** instead of Prisma.\n\nThree reasons:\n1. **Lighter** — no code generation step, no separate migration runner unless I want one\n2. **Type inference at the query level** — `db.select().from(appointments)` already has the right shape, no generated client to keep in sync\n3. **SQL-in-TypeScript** — I can drop to raw SQL via `` sql`...` `` for things like `count(*) filter (where ...)` aggregations",
        code:
          "// The no-show client query — painful in Prisma, clean in Drizzle\nimport { sql } from 'drizzle-orm';\n\nconst rows = await db\n  .select({\n    clientId: appointments.clientId,\n    clientName: clients.name,\n    total: sql<number>`count(*)`,\n    noShows: sql<number>`count(*) filter (where ${appointments.status} = 'no_show')`,\n  })\n  .from(appointments)\n  .leftJoin(clients, eq(clients.id, appointments.clientId))\n  .where(eq(appointments.professionalId, professionalId))\n  .groupBy(appointments.clientId, clients.name);",
        deepDive:
          "There's a Supabase gotcha that cost me half a day: the pooled connection string uses **PgBouncer in transaction mode**, which rotates server connections between clients. Prepared statements are per-connection state, so they break when PgBouncer hands your next query to a different underlying connection.\n\nThe error was cryptic: `prepared statement \"s_42\" does not exist`. The fix is documented but easy to miss: pass `prepare: false` to the postgres-js driver. Turning off prepared statements trades a tiny bit of performance for compatibility with the pooled connection — worth it for a serverless deployment.",
        learnMore: "Why did Tiago use prepare: false on postgres-js for Odys?",
      },
      {
        title: "5. The payment system — Stripe + hand-rolled PIX",
        content:
          "**Stripe** handles subscriptions — professionals pay Odys monthly in four tiers (Free / R$39 / R$79 / R$149) with a 14-day Pro trial. Plan changes happen **only** via signed Stripe webhook — there's no client path to escalate plan.\n\nFor client-to-professional payments, I integrated **PIX**, Brazil's instant payment rail. PIX QR codes follow a spec from Banco Central — TLV encoding, CRC16 checksum, length-delimited fields. I hand-rolled it from the spec instead of using a library.",
        code:
          "// lib/pix.ts — EMV BR Code generator (excerpt)\nfunction field(id: string, value: string): string {\n  const len = value.length.toString().padStart(2, '0');\n  return id + len + value;\n}\n\nfunction crc16(payload: string): string {\n  let crc = 0xFFFF;\n  for (const char of payload) {\n    crc ^= char.charCodeAt(0) << 8;\n    for (let i = 0; i < 8; i++) {\n      crc = (crc & 0x8000) ? ((crc << 1) ^ 0x1021) : (crc << 1);\n      crc &= 0xFFFF;\n    }\n  }\n  return crc.toString(16).toUpperCase().padStart(4, '0');\n}",
        deepDive:
          "I built PIX from scratch because the libraries I found pulled in 50+ dependencies for what is ultimately a TLV encoder plus a CRC16/CCITT-FALSE checksum. The spec is a ~20 page PDF from Banco Central — readable in an afternoon.\n\nThe webhook security model for Stripe is worth calling out: I verify every event via `stripe.webhooks.constructEvent` with the signing secret. Session metadata carries `professionalId` and `plan`, so when `checkout.session.completed` fires I can look up the right row without round-tripping through Stripe. On `customer.subscription.deleted`, the plan resets to `\"free\"` and the Stripe IDs are cleared. It's the only place in the codebase that writes to the `plan` column.",
        learnMore: "How does Odys handle Stripe webhooks securely?",
      },
      {
        title: "6. The AI assistant — with guardrails",
        content:
          "After the core features were live, I added a chat assistant for professionals. It answers questions like _'how many sessions did I have in March?'_ or _'which clients miss the most appointments?'_.\n\nThe trick was making it **safe**: the model uses Groq's tool-calling with three tools (`get_stats`, `get_upcoming`, `get_no_show_clients`). Each tool runs a scoped SQL query with the professional's ID enforced at the SQL layer — **not** trusted to the model.",
        code:
          "// Four layers of guardrails\n// 1. Plan check BEFORE we spend a single Groq token\nif (!canUseFeature(plan, 'assistant', trialEndsAt)) {\n  return { status: 403 };\n}\n\n// 2. Tenant scoping at the SQL layer — never in the prompt\nasync function get_no_show_clients({ professionalId }) {\n  return db.select(...).where(eq(appointments.professionalId, professionalId));\n}\n\n// 3. Deterministic math — the model doesn't multiply\nconst revenue = completedCount * sessionPrice; // computed in the tool\n\n// 4. Unknown tools return errors, never throw\nif (!TOOLS_MAP[toolName]) return { error: 'unknown tool' };",
        deepDive:
          "There are four layers of defense:\n\n1. **Plan check before the Groq client is even initialized** — saves money on unauthorized traffic and makes the auth layer independent of the AI stack.\n2. **Tenant scoping at the SQL layer** — the `professionalId` comes from the server-authenticated session, never from the model. Every tool's query is `WHERE professional_id = $1`. The model literally cannot see another tenant's data because it cannot call anything except these three tools, and these three tools cannot join across tenants.\n3. **Deterministic math** — revenue is computed by the tool (`completed_count * sessionPrice`), not by asking the model to multiply. Models are unreliable at arithmetic under pressure.\n4. **System prompt rules** — 'always use tools, never invent numbers, format BRL, respond in Portuguese.' Unknown tool names return an error object instead of throwing, so a prompt-injected 'call get_admin_data' just fails politely.\n\nThe prompt engineering itself is design: 'TAXA DE NO-SHOW → use get_stats' vs 'QUAIS clientes faltam mais → use get_no_show_clients' explicitly disambiguates two similar intents that the model originally confused.",
        learnMore: "What are the four layers of guardrails on the Odys AI assistant?",
      },
      {
        title: "7. The reminder cron — idempotent by design",
        content:
          "Every day at 08:00, a Vercel cron hits `/api/cron/reminders`. Three jobs in one endpoint:\n\n1. **24h reminders** — appointments starting in `[now+23h, now+25h]`\n2. **1h reminders** — appointments starting in `[now+50min, now+70min]`\n3. **Trial expiry emails** — when `trialDaysLeft` is 3 or 1\n\nThe ±1h window isn't arbitrary — it's a resilience pattern. Cron runs once a day, so 'exactly 24h' would miss any appointment whose 24h mark falls between runs.",
        code:
          "// Idempotency via a flag + time window\nconst appointments = await db.select()\n  .from(appointments)\n  .where(and(\n    eq(appointments.status, 'confirmed'),\n    eq(appointments.reminderSent24h, false),           // idempotency\n    gte(appointments.startsAt, addHours(now, 23)),     // lower bound\n    lte(appointments.startsAt, addHours(now, 25)),     // upper bound\n  ));\n\nfor (const appt of appointments) {\n  const ok = await sendWhatsApp(...);\n  if (ok) await db.update(appointments)\n    .set({ reminderSent24h: true })\n    .where(eq(appointments.id, appt.id));\n}",
        deepDive:
          "'Belt and suspenders' is the right mental model. The `reminder_sent_24h` boolean flag prevents double-sending. The 2-hour window prevents missing an appointment on a missed cron run. Together they guarantee: every confirmed appointment receives exactly one 24h reminder, even if the cron fails for a day.\n\nAuth on cron endpoints is a dual-scheme: either `Authorization: Bearer <CRON_SECRET>` (what Vercel sends automatically) OR a custom `x-cron-secret` header (for manual debug triggers). Returns 401 if neither matches. Cron secrets are in environment variables, not code.\n\nFinally, the reminder job re-checks plan features _inside_ the loop — in case the professional downgraded between the cron being scheduled and it firing. A Free-plan user who downgraded shouldn't still get reminders.",
        learnMore: "Why is the reminder cron window 2 hours instead of exact 24h?",
      },
      {
        title: "8. The deployment stack",
        content:
          "Odys runs across multiple services, each picked for a specific reason:\n\n- **Vercel** — Next.js app (auto-deploys from `main`)\n- **Supabase** — PostgreSQL + Auth + Storage\n- **Railway** — Evolution API (Docker container)\n- **Upstash Redis** — rate limiting (serverless-friendly, no TCP pool)\n- **Stripe** — subscriptions + PIX receipts\n- **Resend** — transactional email\n- **Sentry** — error monitoring\n- **PostHog** — product analytics\n- **GitHub Actions** — CI (tsc, eslint, build)",
        deepDive:
          "Rate limiting deserves a callout. I run three isolated Upstash Redis limiters with distinct key prefixes:\n\n- `rl:booking` — 5 requests per 10 minutes per IP (prevents booking spam)\n- `rl:api` — 60 requests per minute per IP (generic API protection)\n- `rl:onboarding` — 3 requests per hour per IP (prevents signup farming)\n\nThe reason for three prefixes instead of one: I can change any one without affecting the others. If booking gets DDoS'd I can tighten that limit in isolation. Distinct prefixes = distinct counters in Redis = no collision.\n\nObservability: Sentry for errors (stack traces, source maps), PostHog for product funnels (trial → paid conversion). Two tools because they solve different problems. Trying to shoehorn PostHog into error tracking or Sentry into analytics always ends badly.",
        learnMore: "How is rate limiting implemented in Odys?",
      },
      {
        title: "9. The honest assessment",
        content:
          "Odys is live in production at [odys.com.br](https://odys.com.br) but **doesn't have meaningful user traction yet**. I've been focused on the engineering and product rather than distribution.\n\nThe codebase: **112 TypeScript files**, **20 API routes**, **10 Postgres tables**, **19 WhatsApp message templates** as named functions, 4 plan tiers. Production-grade patterns: rate limiting, webhook verification, watchdog crons, monitoring, idempotent jobs. But it hasn't been stress-tested at scale because the traffic isn't there.\n\nI'm deliberately open about this. The product is technically sound. Distribution is the next chapter — and the one that needs a team.",
        deepDive:
          "Saying 'my product has no users yet' out loud is uncomfortable but it's the right move. Recruiters respect honesty more than exaggeration, and any exaggeration is a trap waiting to snap shut in a technical interview. The honest version lets me talk about what I _did_ achieve — the architecture, the reliability patterns, the hand-rolled PIX integration, the AI guardrails — without having to defend an inflated user count.\n\nThings I'd do differently if I had a team or a year: stress test the WhatsApp watchdog layer (that's the first thing that would break at 10× load), add a nightly Stripe reconciler to catch webhook drift, introduce a formal state machine library for appointment transitions, and write real evals for the AI assistant instead of the manual regression checklist I use now.",
        learnMore: "What would break first if Odys went from 10 to 10,000 users?",
      },
      {
        title: "10. The takeaway",
        content:
          "Odys shows **end-to-end ownership** as a solo builder:\n\n- Market research and user interviews\n- Product design and technical architecture\n- Full-stack implementation (frontend, backend, AI layer)\n- Production deployment and monitoring\n- Payment integration and webhook handling\n- Multi-tenant data isolation\n- AI orchestration with safety guardrails\n\nNo team to lean on, no specs handed over, every decision was mine. That's the muscle I'm looking to bring to a product engineering role — the ability to translate a vague user problem into a shippable, observable, safe product.",
        deepDive:
          "The lesson I keep coming back to: **a solo builder's bottleneck is never technology, it's scope discipline**. Odys could have been twice as big and half as finished. Every feature I _didn't_ build is as important as the ones I did. No in-app video calls. No multi-language support. No mobile apps. No team features. Each of those is a yes-I-could-build-it-but-should-I decision, and saying no is the hardest part.\n\nIf you're interviewing for a role where one person has to own a whole surface area — a Product Engineer, a Founding Engineer, a Solutions Engineer — this is the muscle you want them to have. Odys is my evidence I have it.",
        learnMore: "What does founder-level ownership mean to Tiago?",
      },
    ],
  },

  "inspection": {
    title: "How the Inspection Management API was built",
    emoji: "🛠️",
    liveUrl: "https://inspection-management-api.onrender.com/docs",
    steps: [
      {
        title: "1. The origin — from research to production",
        content:
          "This project came from my **MSc thesis** on road damage detection with YOLOv8. The thesis trained a model, measured mAP, and wrote it up — classic research. But it stopped short of something a municipality could actually use.\n\nThe Inspection Management API is the 'what would you do with that model in production' companion: a REST API where inspectors report road damage with photos, and an AI model classifies the damage type and severity automatically, with a human-readable rationale. Humans stay in control — every AI decision can be overridden, and overrides are tracked.",
        deepDive:
          "The gap between research and production is the exact place where most AI projects die. A thesis measures test-set accuracy. A production system has to deal with: authenticated users, data isolation between tenants, background processing for slow AI calls, schema migrations, rollback plans when the model changes, and — critically — **letting a human disagree with the AI and tracking it**.\n\nThat last part is why I built override tracking. In the real world, inspectors know things the model doesn't: 'yes the model says pothole but this stretch of road is going to be resurfaced next month anyway, it's low priority.' The system has to honor that judgment _and_ remember that the AI originally said something different. Otherwise you can't measure how often the model is wrong.",
        learnMore: "How does the Inspection API bridge research and production?",
      },
      {
        title: "2. The stack choice",
        content:
          "**FastAPI + PostgreSQL + SQLAlchemy + Alembic**.\n\n- **FastAPI** — async-first (important because AI vision calls can take 2–3 seconds), automatic OpenAPI docs, Pydantic validation built-in\n- **PostgreSQL** — boring and reliable, the right default\n- **SQLAlchemy 2.0** — mature, supports `hybrid_property` for computed fields (I use this for override tracking)\n- **Alembic** — version-controlled schema migrations, non-negotiable for any real API",
        code:
          "# app/main.py — FastAPI app with layered routers\nfrom fastapi import FastAPI\nfrom app.routers import auth, inspections, admin\n\napp = FastAPI(title='Inspection Management API', version='1.0.0')\napp.include_router(auth.router)\napp.include_router(inspections.router)\napp.include_router(admin.router)\n\n# Swagger docs auto-generated at /docs",
        deepDive:
          "The 'boring stack' choice is deliberate. For a portfolio project demonstrating production engineering skills, I wanted reviewers to see patterns they recognize immediately: a FastAPI layered architecture (`routers` → `services` → `models`), standard SQLAlchemy with relationships, Alembic for migrations, Docker for deployment. Nothing exotic.\n\nThe exotic choices (the vision AI, the override tracking hybrid property, the image compression pipeline) live inside this standard skeleton. That's how you make a project both impressive _and_ readable — put the creative work in places where it will be appreciated, and use conventional patterns everywhere else so the reviewer doesn't have to decode your architecture before they can judge the interesting parts.",
        learnMore: "Why FastAPI instead of Flask or Django for the Inspection API?",
      },
      {
        title: "3. The AI classification service",
        content:
          "The AI service has **two paths**:\n\n- **Vision** (for images) → uses the **Groq SDK directly** with Llama 4 Scout vision model\n- **Text-only** (for notes) → uses **LangChain's `.with_structured_output()`**\n\nI tried LangChain's `ChatGroq` wrapper for images first. It doesn't forward base64 images properly — I spent a frustrating afternoon debugging before falling back to the native SDK.",
        code:
          "# app/services/ai_service.py\nclass AIService:\n    async def classify_with_image(self, notes, image_b64):\n        compressed = self._compress(image_b64)  # Pillow, max 1024px, 75% JPEG\n        resp = await self.groq_client.chat.completions.create(\n            model='meta-llama/llama-4-scout-17b-16e-instruct',\n            messages=[{\n                'role': 'user',\n                'content': [\n                    {'type': 'text', 'text': PROMPT},\n                    {'type': 'image_url', 'image_url': {\n                        'url': f'data:image/jpeg;base64,{compressed}'\n                    }},\n                ],\n            }],\n        )\n        return self._parse(resp.choices[0].message.content)\n\n    async def classify_with_text(self, notes):\n        chain = self.text_llm.with_structured_output(AIClassification)\n        return await chain.ainvoke(PROMPT.format(notes=notes))",
        deepDive:
          "The 'drop the framework when the framework gets in the way' decision is worth internalizing. LangChain is great for composing chains of text-only LLM calls. It is not great for vision — the abstraction doesn't pass through what Groq's native SDK needs. The right move is to use LangChain where it helps and drop it where it doesn't, not to force everything through one abstraction.\n\nFor text classification I keep LangChain because `.with_structured_output()` is genuinely useful: it configures function calling under the hood so the model returns a type-safe Pydantic object matching my `AIClassification` schema, with enum fields for `damage_type` and `severity`. No JSON parsing, no model hallucinating invalid categories, no string-to-enum conversion. That abstraction earns its keep.",
        learnMore: "Why does the Inspection API use two different AI code paths?",
      },
      {
        title: "4. The background task pattern",
        content:
          "When an inspection is created, the API returns a **201 immediately** and runs the AI classification as a FastAPI `BackgroundTask`. The frontend polls `GET /inspections/{id}` every 3 seconds until `is_ai_processed = true`.\n\nThis pattern matters: AI calls are slow (2–3 seconds for vision) and sometimes fail. Putting them in the request path would mean long waits and frequent timeouts. Background processing keeps the API responsive.",
        code:
          "# app/routers/inspections.py\n@router.post('/inspections', status_code=201)\nasync def create_inspection(\n    data: InspectionCreate,\n    background_tasks: BackgroundTasks,\n    db: Session = Depends(get_db),\n    user: User = Depends(get_current_user),\n):\n    inspection = inspection_service.create(db, data, user.id)\n    background_tasks.add_task(process_with_ai, inspection.id)\n    return inspection  # 201 returned immediately\n\nasync def process_with_ai(inspection_id: int):\n    # Opens its OWN database session — request session is already closed\n    db = SessionLocal()\n    try:\n        result = await ai_service.classify(...)\n        inspection_service.update_ai_fields(db, inspection_id, result)\n    finally:\n        db.close()",
        deepDive:
          "The subtle bug with FastAPI's `BackgroundTasks` is the database session lifetime. When `create_inspection` returns, FastAPI closes the request's `Session` (that's what `Depends(get_db)` cleans up). If the background task still holds a reference to that session, it'll blow up with a 'session is closed' error the moment it tries to commit.\n\nThe fix is exactly what the snippet shows: open a **new** `SessionLocal` inside the background task, use it, close it explicitly in a `finally` block. The two sessions never overlap. The request-scoped session dies with the request, the task-scoped session lives as long as the task needs it.\n\nThis is one of those 'obvious in hindsight, painful in the moment' bugs. The traceback never mentions 'session', it talks about `DetachedInstanceError` or stale ORM objects.",
        learnMore: "How does FastAPI handle background tasks for AI processing?",
      },
      {
        title: "5. Override tracking with hybrid_property",
        content:
          "Each inspection has **two parallel sets of fields**:\n\n- Editable: `damage_type`, `severity` (a user can change these)\n- AI: `ai_damage_type`, `ai_severity` (immutable after processing)\n\nA SQLAlchemy `hybrid_property` called `is_ai_overridden` computes on-read whether the human has changed anything. No redundant storage, always accurate.",
        code:
          "# app/models/inspection.py\nclass Inspection(Base):\n    __tablename__ = 'inspections'\n\n    id = Column(Integer, primary_key=True)\n    # Editable by the human\n    damage_type = Column(Enum(DamageType), nullable=False)\n    severity = Column(Enum(SeverityLevel), nullable=False)\n    # Immutable — set once by the AI\n    ai_damage_type = Column(Enum(DamageType), nullable=True)\n    ai_severity = Column(Enum(SeverityLevel), nullable=True)\n    ai_rationale = Column(Text, nullable=True)\n    is_ai_processed = Column(Boolean, default=False)\n\n    @hybrid_property\n    def is_ai_overridden(self) -> bool:\n        if not self.is_ai_processed or self.ai_damage_type is None:\n            return False\n        return (\n            self.damage_type != self.ai_damage_type\n            or self.severity != self.ai_severity\n        )",
        deepDive:
          "The alternative to a `hybrid_property` is storing a separate `is_overridden` boolean column and updating it on every write. That introduces three problems:\n\n1. **Staleness** — if you forget to update the flag on any write path, it goes wrong silently\n2. **Redundant storage** — the flag is derivable from other columns, so it's not new information\n3. **Migration hell** — when the schema evolves, the flag has to evolve with it\n\nThe `hybrid_property` pattern dodges all three: the 'override' state is computed from the existing columns every time you access it, and the same logic works at the Python level (`inspection.is_ai_overridden` on a loaded object) _and_ at the SQL level if you extend it with a separate `@is_ai_overridden.expression` for queries. Always correct, no sync bugs, no schema changes needed when other fields are added.\n\nThis pattern scales. Any 'derived fact' from existing columns should be a hybrid property before it's a stored column.",
        learnMore: "How does the hybrid_property pattern work for AI override tracking?",
      },
      {
        title: "6. The image compression pipeline",
        content:
          "Groq's vision API has a size limit on base64 images. I added a **Pillow-based compressor** that resizes to max 1024px on the longer side and re-encodes as JPEG at 75% quality before sending.\n\nThis does three things at once: saves tokens (and money), keeps requests within limits, and matches the resolution the vision model was trained on (higher resolution doesn't help classification accuracy for damage detection at this scale).",
        code:
          "# app/services/image_processing.py\nfrom PIL import Image\nfrom io import BytesIO\nimport base64\n\nMAX_DIM = 1024\nJPEG_QUALITY = 75\n\ndef compress(image_b64: str) -> str:\n    data = base64.b64decode(image_b64)\n    img = Image.open(BytesIO(data))\n\n    if max(img.size) > MAX_DIM:\n        img.thumbnail((MAX_DIM, MAX_DIM))  # preserves aspect ratio\n\n    buf = BytesIO()\n    img.convert('RGB').save(buf, format='JPEG', quality=JPEG_QUALITY)\n    return base64.b64encode(buf.getvalue()).decode()",
        deepDive:
          "`thumbnail` is the 'right' resize method in Pillow for this use case — it preserves aspect ratio, does in-place modification, and picks a reasonable resampling filter by default. The alternative, `resize((w, h))`, requires you to calculate the new size and stretches or crops if you get it wrong.\n\nI also do client-side compression in the dashboard (resize to 800px before upload). That means a 4000×3000 smartphone photo becomes ~200KB before it ever leaves the browser. The server-side compression is a second line of defense for edge cases (desktop uploads, API clients, old phones).\n\nThe JPEG quality setting is a real trade-off: 75% is where the visible quality drop starts for most images, but you save 60–70% of the bytes versus 95%. For a classification task where the model just needs to see 'pothole shape' clearly, 75% is plenty.",
        learnMore: "Why does the Inspection API compress images before sending to Groq?",
      },
      {
        title: "7. Auth with strict data isolation",
        content:
          "JWT with `python-jose`, `bcrypt` for password hashing, FastAPI dependency injection for protection.\n\nTwo roles: `user` and `admin`. Regular users can only CRUD **their own** inspections — enforced at the query layer by always filtering on `user_id`. Admins have a separate `/admin/inspections` endpoint group that returns cross-user data.",
        code:
          "# app/core/security.py\ndef get_current_user(\n    token: str = Depends(oauth2_scheme),\n    db: Session = Depends(get_db),\n) -> User:\n    try:\n        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])\n        user_id: int = payload.get('sub')\n    except JWTError:\n        raise HTTPException(401, 'Invalid token')\n    user = db.query(User).get(user_id)\n    if not user:\n        raise HTTPException(401, 'User not found')\n    return user\n\n# app/routers/inspections.py — filter at the query layer\n@router.get('/inspections')\ndef list_inspections(user: User = Depends(get_current_user), db: Session = Depends(get_db)):\n    return db.query(Inspection).filter(Inspection.user_id == user.id).all()\n\n# app/routers/admin.py — explicit admin check\n@router.get('/admin/inspections')\ndef list_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):\n    if user.role != UserRole.admin:\n        raise HTTPException(403, 'Admin access required')\n    return db.query(Inspection).all()",
        deepDive:
          "The key discipline: **authorization happens on the server, always**. There's no 'the frontend will only show admin pages to admins' rationalization. Every protected endpoint explicitly checks the role. Every list endpoint filters on `user_id`. The tests specifically cover cross-user access — user A attempting to GET user B's inspection must return 404, not 403, because 403 leaks that the ID exists.\n\nThe `user_id` filter at the query level is the right place because it's impossible to forget — it's part of the same statement that fetches the data, so there's no 'load then filter' race window. It also composes with other filters and pagination cleanly.\n\nJWT has a refresh-token shaped hole in the design (I didn't implement refresh tokens for this scope), and I'm upfront about that in the README. For a team-scale product I'd add refresh tokens and rotate them on every use.",
        learnMore: "How does the Inspection API prevent one user from accessing another's data?",
      },
      {
        title: "8. Testing with a real database",
        content:
          "**31 Pytest tests** covering auth, CRUD, data isolation, filtering, pagination, sorting, admin endpoints, and validation. The tests run against a **real PostgreSQL** database (not mocks) — because ORM bugs are exactly the kind of thing that mocks hide.\n\nGitHub Actions CI spins up a Postgres 15 service container with health checks, runs Alembic migrations, then runs the test suite on every push.",
        code:
          "# .github/workflows/ci.yml\nname: CI\non: [push, pull_request]\njobs:\n  test:\n    runs-on: ubuntu-latest\n    services:\n      postgres:\n        image: postgres:15\n        env:\n          POSTGRES_PASSWORD: postgres\n          POSTGRES_DB: test_db\n        options: >-\n          --health-cmd pg_isready\n          --health-interval 10s\n          --health-timeout 5s\n          --health-retries 5\n        ports:\n          - 5432:5432\n    steps:\n      - uses: actions/checkout@v4\n      - uses: actions/setup-python@v5\n        with: { python-version: '3.11' }\n      - run: pip install -r requirements.txt\n      - run: alembic upgrade head\n        env:\n          DATABASE_URL: postgresql://postgres:postgres@localhost/test_db\n      - run: pytest --tb=short -q\n        env:\n          DATABASE_URL: postgresql://postgres:postgres@localhost/test_db\n          SECRET_KEY: test-secret",
        deepDive:
          "The 'mocks hide ORM bugs' claim isn't abstract — I've been burned by it personally on other projects. A mocked session returns whatever you tell it to, so a query that would have failed in production (wrong column name, missing join, SQLAlchemy relationship bug) passes the unit test. You find out when you deploy.\n\nRunning Postgres as a service container costs ~20 seconds of CI time per run. That's a great trade. Every test exercises the same ORM, the same migrations, the same types as production. The only difference is test data. The tests are integration tests in the literal sense: they test the integration between your code, the ORM, and the database.\n\nI use a helper `unique_email()` (UUID-based) to ensure tests don't collide when they run in parallel. Alembic runs once before the test suite; each test uses a transaction that rolls back at the end. Fast, isolated, real.",
        learnMore: "Why does the Inspection API use real PostgreSQL in tests instead of mocks?",
      },
      {
        title: "9. Deployment",
        content:
          "The API is a **Docker container on Render's free tier**. The companion frontend (`inspection-dashboard.vercel.app`) is vanilla HTML/CSS/JS on Vercel — no React, no build tools.\n\nThe backend auto-deploys on push to `main`. Alembic migrations run on container startup. The frontend polls the backend for AI status updates and shows the classification once it's ready.",
        code:
          "# Dockerfile\nFROM python:3.11-slim\nWORKDIR /app\nCOPY requirements.txt .\nRUN pip install --no-cache-dir -r requirements.txt\nCOPY . .\nENV PORT=8000\nCMD sh -c \"alembic upgrade head && \\\n           uvicorn app.main:app --host 0.0.0.0 --port ${PORT}\"",
        deepDive:
          "The `alembic upgrade head` on startup is a deliberate choice for a single-instance deployment. For multi-instance setups you'd want a separate migration step (so only one instance runs migrations while others boot), but for a single container on Render it's fine — the container won't accept traffic until `uvicorn` is up, and `alembic upgrade head` is idempotent, so running it twice is safe.\n\nThe dashboard being vanilla JS is philosophical: for a portfolio project that's fundamentally about the API, I didn't want to bury the API work under a React rewrite. The frontend exists to show the API works end-to-end, not to be the focus. A 700-line `index.html` and a 900-line `app.js` handle everything: auth, CRUD, polling, filtering, pagination. Less code overall than any equivalent React + state management + build tooling setup.",
        learnMore: "Why is the Inspection dashboard written in vanilla JavaScript?",
      },
      {
        title: "10. The takeaway",
        content:
          "The Inspection API demonstrates a specific shape of engineering:\n\n- **Clean layered architecture** (routers → services → models)\n- **Async-first backend** for AI integration\n- **Production AI patterns** — vision + text, structured output, background processing\n- **Human-in-the-loop design** with override tracking\n- **Comprehensive testing** with a real database in CI\n- **Version-controlled schema evolution** via migrations\n\nIt's the 'real' companion to my academic thesis — research turned into a shippable API with the patterns an interviewer would expect to see.",
        deepDive:
          "If you're a hiring manager looking at portfolio projects, the signal you want from an API project is: do they understand that the interesting work is 5% of the code and 95% of the code is the skeleton that makes that 5% deployable, testable, and maintainable? The Inspection API is that skeleton around the AI vision call. The AI is the creative part, but what makes it a real product is the auth, the migrations, the tests, the background tasks, the override tracking, and the deployment.\n\nEvery junior-to-mid candidate can train a model. Not every candidate can put that model behind an API that a team could take over on day one.",
        learnMore: "What does production-ready AI integration look like?",
      },
    ],
  },

  "chatbot": {
    title: "How this chatbot was built",
    emoji: "🤖",
    liveUrl: "https://chatbot.tifortunato.com",
    steps: [
      {
        title: "1. The starting point — generic PDF chatbot",
        content:
          "It began as a generic **RAG PDF chatbot** — upload any PDF, ask questions about it. A classic 'RAG 101' project: ingest, embed, store, retrieve, generate. Nothing fancy.\n\nBut I realized I had a stronger use case: turn it into **my own interactive career assistant**. Instead of recruiters reading a static CV, they could ask natural questions and get sourced, streamed answers.",
        deepDive:
          "The pivot from 'tool' to 'product' is worth calling out. A generic PDF chatbot is a demo — interesting for 30 seconds, then you close the tab. A career chatbot is a **product** because it has an audience (recruiters), a purpose (evaluate a candidate), and a success metric (did they walk away understanding the person?).\n\nThat reframe changed every design decision downstream. A demo optimizes for 'look what the technology can do'. A product optimizes for 'does the user feel they got what they came for'. The second question is a lot harder and leads you into UX decisions the demo version never needs to make.",
        learnMore: "What made Tiago pivot from a generic PDF chatbot to a career assistant?",
      },
      {
        title: "2. The pivot — structured knowledge bases",
        content:
          "First big change was the **knowledge base**. Instead of ingesting random PDFs, I wrote structured markdown files documenting my projects, background, and technical decisions.\n\nI also rewrote the system prompt with a **Professional Talent Assistant persona** focused on recruiters: honest, technical, no hallucination, source-grounded, markdown-formatted.",
        code:
          "# data/knowledge_base.md — excerpt\n## Quick Reference — Common Recruiter Questions\n\n### Who is Tiago Fortunato\nTiago Fortunato is a Product Engineer and Founder based\nin Berlin, Germany. He has an MSc in Software Engineering\nfrom the University of Europe for Applied Sciences (2026)\nand a BSc in Mechanical Engineering from UERJ in Brazil.\nHe is the sole founder and developer of Odys...",
        deepDive:
          "The knowledge base shape matters as much as the content. Section-aware chunking works by splitting on markdown headings (`#`, `##`, `###`), so the physical structure of the document directly controls what the retriever treats as a 'chunk'.\n\nI learned this the hard way: the first iteration had a giant flat 'About Me' section that the splitter broke in awkward places, losing context. The rewrite has lots of short `##` sections with self-contained answers — a 'Quick Reference' block at the top that explicitly answers the most common questions. That way, for a query like 'who is Tiago?', the retriever can pull a single coherent chunk instead of assembling fragments.\n\nThe system prompt also matters more than most people think. The rules I wrote out explicitly — 'every factual claim must be grounded in context', 'never invent URLs', 'adapt language to the audience', 'use markdown formatting' — each one came from observing a specific failure in an earlier version.",
        learnMore: "How is the career knowledge base structured for optimal retrieval?",
      },
      {
        title: "3. The first deploy (Render)",
        content:
          "The chatbot first went live on **Render's free tier**. Fast to set up, free, worked.\n\nBut two problems emerged:\n\n1. **Cold starts** — Render's free tier spins down after 15 minutes of inactivity. First visitor gets a 50-second cold start, which kills engagement.\n2. **I wanted AWS experience on my portfolio** — Render is a managed service hiding the complexity. For a learning project, that's the opposite of what I wanted.",
        deepDive:
          "The cold-start problem is subtle. It's not 'sometimes slow' — it's 'the literal first impression for a brand new recruiter is a 50-second blank page', because the very first visit of the day triggers the cold start. The people who matter most to the product (first-time visitors) get the worst experience by design.\n\nI tried a band-aid first: a `keep_alive` background task inside the app that pings `/health` every 10 minutes. That prevents the spin-down as long as the container is running. But it's fragile — if Render restarts the container for any reason, the keep-alive restarts too, and the next visitor still hits a cold start. Also, it violates the free tier's implicit contract (it's supposed to spin down), which is uncomfortable.\n\nMoving to a box I own (EC2) fixed both issues — always on, and I learned real infrastructure work along the way.",
        learnMore: "Why did Tiago migrate the chatbot from Render to AWS EC2?",
      },
      {
        title: "4. The AWS migration",
        content:
          "I moved the chatbot to **AWS EC2** (`t3.micro`). This meant setting up all the pieces manually:\n\n- **Docker** container with `--restart unless-stopped`\n- **Nginx reverse proxy** on 80/443\n- **Let's Encrypt SSL** with auto-renewal cron\n- **Custom domain** (`chatbot.tifortunato.com`) via Namecheap DNS\n- **Elastic IP** so the address doesn't change on restart\n\nAll manual. No managed service hiding the complexity. The point was learning production infrastructure.",
        code:
          "# /etc/nginx/conf.d/chatbot.conf\nserver {\n  listen 443 ssl;\n  server_name chatbot.tifortunato.com;\n  ssl_certificate /etc/letsencrypt/live/chatbot.tifortunato.com/fullchain.pem;\n  ssl_certificate_key /etc/letsencrypt/live/chatbot.tifortunato.com/privkey.pem;\n\n  location / {\n    proxy_pass http://127.0.0.1:8000;\n    proxy_http_version 1.1;\n    proxy_buffering off;            # critical for SSE streaming\n    proxy_cache off;\n    proxy_set_header Connection '';\n    proxy_set_header Host $host;\n  }\n}",
        deepDive:
          "`proxy_buffering off` is the single most important line. By default, Nginx buffers the entire response before sending it to the client — which completely defeats Server-Sent Events (SSE) for streaming tokens. The user would see nothing for 10 seconds, then get the whole answer at once.\n\nWith buffering off, Nginx passes each SSE chunk through immediately. The `proxy_http_version 1.1` and empty `Connection` header are also needed to keep the connection alive for streaming (HTTP/1.0 would close after the first response).\n\nThe rest of the setup is standard production hygiene: container binds to `127.0.0.1` (localhost only) so Nginx is the only public-facing surface, Let's Encrypt via `certbot --nginx` handles the HTTPS block and the redirect, and a cron entry runs `certbot renew` daily to keep the cert fresh. The Elastic IP means the DNS never has to change.",
        learnMore: "How is the chatbot deployed on AWS EC2 with Docker, Nginx, and HTTPS?",
      },
      {
        title: "5. The retrieval problem — hybrid search",
        content:
          "Early answers were hit-or-miss. When asked _'what's your tech stack?'_, the chatbot sometimes missed relevant chunks. The culprit was pure semantic search — it handles meaning well but misses exact technical terms.\n\nThe fix was **hybrid search**:\n- **ChromaDB** for semantic search (embeddings)\n- **BM25** for keyword search (exact matches)\n- **Reciprocal Rank Fusion (RRF)** to combine them\n\nSemantic catches 'databases' → 'PostgreSQL'. BM25 catches 'FastAPI' → `FastAPI`. RRF fuses both without needing a tuning parameter.",
        code:
          "# app/services/retrieval.py — hybrid search with RRF\ndef _hybrid_search(query, k=10, allowed_files=None):\n    # 1. Semantic search\n    semantic = vector_store.similarity_search(query, k=k*2, filter=...)\n    # 2. BM25 keyword search\n    bm25 = _bm25_search(query, k=k*2)\n    # 3. Reciprocal Rank Fusion\n    scores = {}\n    RRF_K = 60  # standard constant\n    for rank, doc in enumerate(semantic):\n        key = doc.page_content[:100]\n        scores[key] = scores.get(key, 0) + 1 / (rank + RRF_K)\n    for rank, doc in enumerate(bm25):\n        key = doc['content'][:100]\n        scores[key] = scores.get(key, 0) + 1 / (rank + RRF_K)\n    # Sort by fused score, return top-k\n    return sorted(doc_map.values(), key=lambda d: -scores[key])[:k]",
        deepDive:
          "RRF is elegant because it's **parameter-free**. The alternative, weighted sum — `alpha * semantic + (1-alpha) * bm25` — requires you to pick `alpha`, and the right value changes per query type. RRF sidesteps that: it only uses ranks, not raw scores, and the `1/(rank + 60)` formula gives diminishing returns so highly-ranked items dominate naturally.\n\nThe `60` constant comes from the original RRF paper (Cormack, Clarke, Büttcher 2009) and basically never needs to be tuned. It's effectively a smoothing factor — small enough that rank-1 and rank-2 are clearly different, large enough that a doc appearing in both lists gets a real boost without any single rank dominating.\n\nDocuments that appear in **both** semantic and BM25 results get summed scores, so agreement is rewarded. Documents that appear in only one list still get some score, so neither modality is wasted. It's the closest thing to 'best of both worlds with zero configuration' I've seen in information retrieval.",
        learnMore: "What is Reciprocal Rank Fusion and why is it used in hybrid search?",
      },
      {
        title: "6. The cross-project confusion",
        content:
          "Once I added **separate knowledge base files** for Odys, the Inspection API, and the RAG chatbot itself, a new problem emerged: the LLM would attribute Odys features to the chatbot or vice versa.\n\nThe root cause was that retrieved chunks didn't tell the LLM which **project** they belonged to. For vague queries like 'tell me about Odys', the hybrid search returned some Odys chunks plus some chatbot chunks that matched semantically.\n\nThe fix was two-fold:\n1. **Source labels** — prefix every retrieved chunk with `[SOURCE: PROJECT NAME]`\n2. **Query routing** — a keyword-based classifier that filters retrieval to one project when the question clearly targets it",
        code:
          "# app/services/retrieval.py\nPROJECT_KEYWORDS = {\n    'odys_knowledge.md': ['odys', 'whatsapp', 'drizzle', 'evolution api', ...],\n    'inspection_api_knowledge.md': ['inspection', 'pothole', 'yolo', 'override', ...],\n    'rag_chatbot_knowledge.md': ['rag chatbot', 'bm25', 'rrf', 'hybrid search', ...],\n}\n\ndef _route_query(question: str) -> list[str] | None:\n    lower = question.lower()\n    matched = [f for f, kws in PROJECT_KEYWORDS.items() if any(k in lower for k in kws)]\n    # Scope to one project if exactly one matched\n    if len(matched) == 1:\n        return [matched[0], 'knowledge_base.md']  # always include general profile\n    return None  # no scoping, search everything\n\n# And prefix retrieved chunks for the LLM\ndef _format_context(results):\n    file_to_project = {\n        'odys_knowledge.md': 'ODYS (SaaS product)',\n        'inspection_api_knowledge.md': 'INSPECTION MANAGEMENT API',\n        'rag_chatbot_knowledge.md': 'RAG CAREER CHATBOT (this chatbot)',\n        'knowledge_base.md': 'GENERAL PROFILE',\n    }\n    return '\\n\\n---\\n\\n'.join(\n        f'[SOURCE: {file_to_project[d[\"metadata\"][\"filename\"]]}]\\n{d[\"content\"]}'\n        for d in results\n    )",
        deepDive:
          "The router is intentionally dumb. It's keyword matching — no ML, no LLM call, no embedding. That's a feature: it's deterministic, instant, and when it's wrong (the question is genuinely cross-project) it fails open by returning `None`, which means 'search everything'. Never blocks a legitimate query, just scopes aggressively when it can.\n\nThe source labels work because the LLM's system prompt has an explicit rule: 'when the question targets a specific project, ONLY use chunks whose source matches that project'. Without the labels, the LLM had no way to tell which chunk belonged to which project; with them, it has an explicit boundary to respect.\n\nThe third thing that helps is always including the general `knowledge_base.md` alongside the scoped project file, because questions like 'how does Odys compare to Tiago's other work?' need both contexts. A single-file scope would answer 'just the Odys parts' and miss the comparison.",
        learnMore: "How does query routing prevent the chatbot from mixing up projects?",
      },
      {
        title: "7. The memory problem",
        content:
          "The `t3.micro` has only **1GB of RAM**. Every attempt to make the chatbot 'better' — larger embeddings, more chunks, ingesting the 3MB thesis PDF, bigger context windows — hit OOM errors during Docker build.\n\nThe solution was a combination of three tactics:\n\n1. **Pre-ingest at Docker build time** — the vector store is baked into the image\n2. **Add 1GB of swap space** on the host\n3. **Mount ChromaDB as a persistent volume** — container restarts don't re-ingest",
        code:
          "# Dockerfile — pre-ingest so runtime startup is cheap\nCOPY data/knowledge_base.md ./data/knowledge_base.md\nCOPY data/odys_knowledge.md ./data/odys_knowledge.md\nCOPY data/inspection_api_knowledge.md ./data/inspection_api_knowledge.md\nCOPY data/rag_chatbot_knowledge.md ./data/rag_chatbot_knowledge.md\n\n# Bake the vector store into the image at build time\nRUN python -m app.scripts.ingest_all\n\n# On the host: persistent volume so restarts skip re-ingest\n# sudo docker run -v ~/chatbot-chroma:/app/chroma_db career-chatbot",
        deepDive:
          "The memory arithmetic is tight. FastEmbed alone is ~250MB resident. ChromaDB adds another ~100MB. FastAPI + uvicorn is ~80MB. The Python interpreter + loaded packages is ~120MB. That's ~550MB baseline with no traffic. The other ~400MB of the 1GB is the buffer for actually serving requests and holding context for the LLM call.\n\nIngesting 500+ chunks at startup pushes memory past the limit because the embedding model has to hold the full batch in memory as it embeds. That's what was causing OOM kills during Docker build. Pre-ingesting works because the build environment (with swap on) can absorb the spike, and runtime only needs to read the pre-built SQLite file (which is fast and memory-light).\n\nSwap space is the safety net for the edge cases: a fallback query with unusually large context, a burst of concurrent requests, etc. It's slow (swap IO thrashes), but slow-and-alive beats fast-and-OOM-killed.",
        learnMore: "How does the chatbot run on a 1GB t3.micro without OOM errors?",
      },
      {
        title: "8. The model upgrade — with fallback",
        content:
          "The chatbot started on **Llama 3.1 8B** — fast but shallow. I upgraded to **Llama 3.3 70B** (also free on Groq, just with tighter daily rate limits). Responses became noticeably richer.\n\nThen I added **automatic model fallback**: if the 70B hits its daily rate limit, the chatbot silently switches to 8B for that request. Users never see errors.",
        code:
          "# app/services/retrieval.py\nFALLBACK_MODEL = 'llama-3.1-8b-instant'\n\ndef _is_rate_limit_error(exc) -> bool:\n    # Recursively check ExceptionGroup, __cause__, __context__, full traceback\n    ...\n\ndef _invoke_with_fallback(chain, params, prompt):\n    try:\n        return chain.invoke(params)\n    except Exception as e:\n        if _is_rate_limit_error(e):\n            logger.warning('Primary rate-limited, falling back to %s', FALLBACK_MODEL)\n            fallback_chain = prompt | _get_llm(FALLBACK_MODEL)\n            return fallback_chain.invoke(params)\n        raise",
        deepDive:
          "The subtle trap here was Python 3.11's `ExceptionGroup`. LangChain runs the LLM call inside an async task group, and when the underlying call raises `groq.RateLimitError`, that error gets wrapped in an `ExceptionGroup` before it bubbles out. A naive `except RateLimitError` **won't catch it**, because the exception type isinstance check fails on the group.\n\nI debugged this the hard way — the fallback wasn't firing in production even though the code looked right. The fix is a helper that recursively walks `exc.exceptions` (for ExceptionGroups), `exc.__cause__`, and `exc.__context__`, then falls back to string-matching the full traceback for 'rate limit' / '429' / 'rate_limit_exceeded'. Ugly, but correct.\n\nAlways test fallback paths in production-like conditions. The happy path is easy. The unhappy path is where real products stand out.",
        learnMore: "How does the chatbot handle rate limits with model fallback?",
      },
      {
        title: "9. The evaluation pipeline (RAGAS)",
        content:
          "To measure improvements **objectively**, I built a **RAGAS evaluation script**. It queries the live chatbot with 10 test questions and scores the answers on four metrics:\n\n- **Faithfulness** — are factual claims grounded in the context?\n- **Answer Relevancy** — does the answer address the question?\n- **Context Precision** — are retrieved chunks relevant?\n- **Context Recall** — were the right chunks retrieved?\n\nCritically, I use **Google's Gemini** as the judge, not Groq. Different model = no self-evaluation bias.",
        code:
          "# eval_ragas.py — judge with a different model\nfrom ragas import evaluate\nfrom ragas.metrics import Faithfulness, AnswerRelevancy, ContextPrecision, ContextRecall\nfrom langchain_google_genai import ChatGoogleGenerativeAI\n\njudge = ChatGoogleGenerativeAI(model='gemini-2.5-flash', google_api_key=GOOGLE_API_KEY)\n\nresults = evaluate(\n    dataset=build_dataset(TEST_QUESTIONS),  # runs questions against live chatbot\n    metrics=[Faithfulness(judge), AnswerRelevancy(judge, embeddings),\n             ContextPrecision(judge), ContextRecall(judge)],\n    llm=judge,\n    embeddings=FastEmbeddings(),\n)\nresults.to_pandas().to_csv('ragas_results.csv')",
        deepDive:
          "Using the **same** model as judge and answerer introduces self-evaluation bias — models tend to rate their own outputs higher than a neutral judge would. It's a real effect, measurable in published benchmarks. The fix is to use a different model, ideally a stronger one (Gemini 2.5 Flash here).\n\nRunning RAGAS after each change is what kept me honest. Several 'obvious improvements' I tried actually **hurt** the scores — larger chunk sizes, query expansion, stricter prompts — and I would have shipped them without measurement. The feedback loop matters: if you can't measure whether a change helped, you can't optimize, you can only guess.\n\nFinal scores plateau around 0.52 overall because 8B (the model the evaluator hits most often, since 70B rate-limits faster) has a ceiling. The improvement curve was: 0.49 → 0.52 → 0.52. Not spectacular, but the shape of the curve tells me the retrieval is doing its job and the ceiling is the generation model, not my RAG pipeline.",
        learnMore: "How does RAGAS evaluate the chatbot's quality?",
      },
      {
        title: "10. The UX polish",
        content:
          "Small details that make a big difference for recruiter experience:\n\n- **Streaming SSE** — tokens appear word-by-word like ChatGPT, not one 30-second pause\n- **Conversation persistence** — localStorage keeps the last 10 exchanges, survives page refresh\n- **Curated entry questions** — first visit shows 5 fixed welcoming questions, not random\n- **LLM-generated follow-ups** — after each answer, 3 contextual suggestions generated by a fast 8B call\n- **Markdown links open in new tabs** — custom `marked.js` renderer\n- **Clear friendly errors** — 429 shows 'I'm getting a lot of traffic', not 'HTTP 429'",
        code:
          "// Frontend: custom marked.js renderer for target=\"_blank\" links\nconst renderer = new marked.Renderer();\nrenderer.link = function({ href, title, text }) {\n  return `<a href=\"${href}\" target=\"_blank\" rel=\"noopener noreferrer\">${text}</a>`;\n};\nmarked.setOptions({ breaks: true, gfm: true, renderer });\n\n// Friendly error handler\ncatch (err) {\n  const msg = err.message || String(err);\n  let friendly;\n  if (msg.includes('429')) friendly = \"I'm getting a lot of traffic right now — try again in a minute!\";\n  else if (msg.includes('network')) friendly = \"I couldn't reach the server. Check your connection.\";\n  else friendly = `Something went wrong: ${msg}`;\n  bubble.textContent = friendly;\n}",
        deepDive:
          "The entry-question curation was an **explicit UX lesson** someone taught me: on the welcome screen, random specific questions can overwhelm a first-time visitor. If the first thing they see is 'Why Drizzle over Prisma?', they don't know who Tiago is yet — that's too deep. The fixed entry set (Tell me about yourself → What projects → Walk me through each project) is a funnel from broad to deep.\n\nAfter the first interaction, the LLM-generated contextual follow-ups take over. A fast 8B call generates 3 questions based on the answer that was just given. The user never sees 'what is Docker' after an answer about WhatsApp — they see 'how does the watchdog detect disconnected sessions' or 'why 2 hours instead of exact 24h'.\n\nThe streaming + markdown rendering combo is fussy. Tokens arrive in chunks that break in the middle of markdown syntax, so I re-run `marked.parse()` on the full accumulated text every time a token arrives. Naive, but fast enough at Groq's streaming rate.",
        learnMore: "What UX decisions make the chatbot feel natural to use?",
      },
      {
        title: "11. The story mode (this!)",
        content:
          "The feature you are using **right now** is the most recent addition.\n\nThe insight came from a real UX complaint: _'the random questions are too specific for a first visit, I don't know where to start'_. The fix was two-layered:\n\n1. Fix the first 5 suggestions to a curated welcoming set\n2. Turn long 'walk me through how X was built' answers into **step-by-step guided tours** with Continue / Deep Dive buttons\n\nThe story is rendered client-side from structured data — no LLM call per step, instant navigation, consistent output every time.",
        deepDive:
          "The architectural question was: should each step be an LLM generation, or should the story be static client-side data?\n\nI went with **static client-side data** for three reasons:\n\n1. **Consistency** — a recruiter clicking through the tour gets the same narrative every time. LLM generations would be consistent-ish but not exactly.\n2. **Latency** — no API round-trip between steps. Click Continue, next step renders in 10ms.\n3. **Cost** — these steps would be the most-read content on the site. Even a fast 8B call per step adds up.\n\nDeep dives are also static for the same reasons. The 'Ask about this' button is where the LLM comes back in — it takes the step's contextual question and sends it through the normal RAG pipeline, so the user can freely explore beyond what's pre-written.\n\nThat split is the right shape. Pre-write the narrative backbone; use the LLM for the open-ended exploration around it.",
        learnMore: "How does the guided tour mode work technically?",
      },
      {
        title: "12. The takeaway",
        content:
          "The hardest part wasn't any single feature — it was learning **when to stop adding features**.\n\nEvery improvement cycle had diminishing returns. The RAGAS scores plateaued because the free-tier model has a ceiling. Some 'obvious improvements' actually hurt the scores (query expansion, stricter prompts, bigger chunks).\n\nI learned to:\n- Ship what works rather than chase numbers\n- Measure **before** optimizing\n- Be honest when something didn't help and revert it\n- Write down the reason for every decision so future-me can find it",
        deepDive:
          "Measurement culture is what separates 'I think this is better' from 'this is measurably better'. The RAGAS eval loop — even though the scores plateaued — was worth it because it told me definitively which changes helped and which didn't. Without it, I would have shipped worse versions with more confidence.\n\nThe final state of the chatbot is not some local maximum I stumbled into. It's what survived after a lot of 'let me try X', measuring, and rolling back the ones that hurt. The story mode is the only change I shipped without measuring first, and that's because it's a UX change that RAGAS doesn't capture (RAGAS measures answer quality, not navigation experience).\n\nThe takeaway for a recruiter: this project shows end-to-end product thinking. Not just 'I can train a model' or 'I can call an API'. But: infrastructure, retrieval engineering, production LLM orchestration, systematic evaluation, UX discipline, and the humility to measure.",
        learnMore: "What are the biggest lessons from building this chatbot?",
      },
    ],
  },
};
