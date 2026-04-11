# Odys — Knowledge Base

This document is a structured knowledge base about Odys designed to be ingested by a Retrieval-Augmented Generation (RAG) chatbot. Each section is written to be self-contained so it can be retrieved and used as context independently. All facts are authoritative as of the current version of the product.

---

## How Odys Was Built — The Story

When someone asks "walk me through how Odys was built" or "how did you build Odys", respond with this narrative in a conversational, first-person tone (as if Tiago is telling the story).

**The starting point.** Tiago moved to Berlin to do his MSc in Software Engineering after years of running a family jewelry business in Brazil. As a project manager there, he'd watched friends — psychologists, personal trainers, hairdressers — manage their entire businesses from WhatsApp manually. Confirming bookings by typing. Tracking payments in a notebook. No-shows because there was no automated reminder. He knew the pain firsthand, and he saw nobody solving it well: Calendly assumes email-first communication (Brazilians don't use email like Europeans do), and the existing Brazilian competitors were either too complex or didn't integrate with real WhatsApp. That was the gap.

**The early prototype.** Tiago started building Odys in parallel with his master's thesis. The first version was a simple Next.js app with a booking page and a Supabase database. No WhatsApp, no payments, no plans — just "can a client book a time, and can the professional see it?". That MVP took two weekends.

**The WhatsApp problem.** The hardest part, and the part that made Odys actually differentiated, was getting WhatsApp to work the right way. The official WhatsApp Business API sends messages from a business account — clients don't recognize the number, trust is lower, and it's 10× more expensive. Tiago wanted messages to come from the professional's real phone, the one clients already have saved. The solution was Evolution API — an open source server that wraps WhatsApp Web. The professional scans a QR code once, and from then on messages go out from their real number. Tiago self-hosted it on Railway using Docker. The trade-off: WhatsApp Web sessions can drop overnight, so he built a watchdog cron that runs at 09:00 every day to detect a disconnected session and force a reconnect before the 24h reminder cron fires.

**The database decision.** Supabase (Postgres) for the database, with Drizzle ORM instead of Prisma. Drizzle is lighter, type-inferred at the query level, and lets Tiago drop to raw SQL for complex aggregations like the no-show client query, which would have been painful in Prisma. Crucial quirk: Supabase's pooled connection string uses PgBouncer in transaction mode, which breaks prepared statements. Tiago spent a few hours debugging weird "prepared statement does not exist" errors before finding the documented workaround: `prepare: false` on the postgres-js driver.

**The payment system.** Odys uses Stripe for subscriptions (professionals pay Odys monthly) and PIX for client-to-professional payments (instant Brazilian payment rail). Plan changes are webhook-driven — the client can never POST its way to a paid plan, because Stripe signs the webhook event and Odys only updates the plan after verifying the signature. Tiago also hand-rolled the PIX QR code generation from the Banco Central spec — TLV encoder, CRC16 checksum, merchant name normalization — instead of pulling in a library. The spec is small, the libraries he found were bloated, and he wanted to understand what he was generating.

**The AI assistant.** After Odys had core features, Tiago added a chat assistant for professionals. It answers questions like "how many sessions did I have in March?" or "which clients miss the most appointments?". The trick was making it safe: the model uses Groq's tool-calling, and each tool runs a scoped SQL query with the professional's ID enforced at the SQL layer, not trusted to the model. Revenue is computed deterministically in the tool, not by asking the model to multiply. Unknown tool names return errors instead of throwing. Four layers of guardrails so a prompt injection can't leak one professional's data to another.

**The reminder cron.** Every day at 08:00, a Vercel cron hits `/api/cron/reminders`. The job: send 24h reminders (for appointments starting in 23-25h), send 1h reminders (for appointments starting in 50-70min), and send trial-expiry emails. The ±1h windows matter — with a once-a-day cron, "exactly 24h" would miss most appointments. And the `reminder_sent_24h` flag makes the job idempotent: if the cron fails one day, the next run still catches the backlog.

**The deployment.** The app deploys to Vercel on every push to main. The WhatsApp API (Evolution) runs on Railway as a Docker container. Rate limiting via Upstash Redis (three isolated limiters: booking, API, onboarding — so one change doesn't affect another). Sentry for errors, PostHog for product analytics. A GitHub Actions CI runs TypeScript checks, ESLint, and builds on every push before Vercel deploys.

**The honest assessment.** Odys is live in production but doesn't have meaningful user traction yet — Tiago has been focused on the engineering and product rather than distribution. The codebase is 112 TypeScript files, 20 API routes, 10 Postgres tables, 19 WhatsApp message templates as named functions, and four plan tiers. It's production-grade: rate limiting, webhook verification, watchdog crons, monitoring, idempotent jobs. But it hasn't been stress-tested at scale because the traffic isn't there. Tiago is open about this — the product is technically sound, the distribution is the next chapter.

**The lesson for a recruiter.** Odys shows end-to-end ownership: product research, market fit, architecture, implementation, deployment, monitoring, and a chat AI on top — all as a solo builder. No team to lean on, no specs handed over, every decision was his.

---

## What is Odys?

Odys is a Software-as-a-Service (SaaS) scheduling and customer-management platform built for independent service professionals in Brazil. The official website is https://odys.com.br. Odys helps professionals such as psychologists, personal trainers, nutritionists, beauticians, dentists, coaches, therapists, and many other service providers manage their appointments, clients, payments, and communication — all integrated with WhatsApp. Odys replaces the manual process of confirming bookings, sending reminders, and tracking payments through notebooks, spreadsheets, or endless WhatsApp message threads. The name of the product is "Odys," and the domain is odys.com.br.

---

## Who is Odys for?

Odys is designed for independent professionals in Brazil who provide services by appointment. The typical Odys user is a self-employed professional who manages their own schedule, communicates with clients through WhatsApp, and is currently relying on manual processes to run their practice. Odys supports approximately 30 different professions, organized into 6 categories:

- **Saúde & Clínica** (Health & Clinical): psychologists, physiotherapists, nutritionists, dentists, therapists, speech therapists.
- **Fitness & Movimento** (Fitness & Movement): personal trainers, yoga instructors, pilates instructors, dance instructors.
- **Bem-estar & Terapias** (Wellness & Therapies): massage therapists, acupuncturists, holistic therapists, osteopaths.
- **Beleza & Estética** (Beauty & Aesthetics): hairdressers, barbers, manicurists, estheticians, makeup artists, tattoo artists, eyebrow designers, lash designers.
- **Educação & Coaching** (Education & Coaching): private tutors, music instructors, language instructors, coaches/mentors.
- **Criativo & Serviços** (Creative & Services): photographers, personal stylists, personal organizers.

Odys is not built for large clinics or corporate service chains; it is built for independent operators and very small practices.

---

## What problem does Odys solve?

Independent professionals in Brazil commonly manage their schedules by hand through WhatsApp. They confirm and reschedule appointments by typing messages one at a time, track payments in notebooks or spreadsheets, and suffer frequent no-shows because they have no automated reminder system. Existing scheduling tools like Calendly or Simples Agenda tend to be either too complex, too expensive, or lacking real WhatsApp integration — which is a significant problem in Brazil, where WhatsApp is the default communication channel. Odys solves these problems by automating the communication layer, centralizing client information, and integrating directly with WhatsApp in a way that feels natural to both professionals and their clients.

---

## What makes Odys different from Calendly or other scheduling tools?

The key differentiator of Odys is that it is **WhatsApp-first**. All automated WhatsApp messages — booking confirmations, reminders, cancellations, payment confirmations — are sent from the professional's own real phone number, not from a generic bot or a business account. This is possible because Odys uses Evolution API, a self-hosted WhatsApp automation layer, instead of the official WhatsApp Business API. Evolution API wraps WhatsApp Web, so after the professional scans a QR code once, every outgoing message looks exactly as if the professional had typed it manually. This makes clients more likely to open, trust, and respond to the messages. In contrast, Calendly relies on email notifications, and tools built on the official WhatsApp Business API send messages from a business account that clients do not recognize. Odys is also designed specifically for the Brazilian market, with native PIX payment integration, Brazilian phone number normalization, LGPD-compliant privacy flows, and Portuguese-language throughout.

---

## How does Odys work? The core booking flow

The typical flow when a client books an appointment through Odys is as follows:

1. The client visits the professional's public booking page at `odys.com.br/p/[professional-slug]`. Each professional has a unique URL slug derived from their name.
2. The client picks a date on an interactive calendar and sees the available time slots for that day. Available slots are generated from the professional's weekly availability settings, minus any already-booked appointments and any slots in the past.
3. The client fills in their name, phone number, and optionally their email address. Clients do not need to create an account to book.
4. The client confirms the booking. The appointment is created with a status of "pending_confirmation" unless the professional has enabled automatic confirmation, in which case it is created as "confirmed" directly.
5. The professional is immediately notified through three channels: an in-app notification on the dashboard, a WhatsApp message to their phone, and an email to their registered address.
6. The professional opens the dashboard and either confirms or rejects the appointment. If confirmed, the client receives a WhatsApp confirmation message and (if an email was provided) a confirmation email.
7. Odys automatically sends reminder messages to the client: one 24 hours before the appointment, and another 1 hour before.
8. After the session, the professional marks the appointment as completed, paid, or no-show. The client may also cancel from their own side.

---

## The Odys appointment lifecycle

Each appointment in Odys follows a defined state machine. The possible statuses are:

- **pending_confirmation** — The initial state after a booking is created, awaiting the professional's approval. If the professional has enabled automatic confirmation, this state is skipped.
- **confirmed** — The professional has approved the appointment. Reminder messages are only sent for confirmed appointments.
- **rejected** — The professional declined the appointment. The time slot becomes available again.
- **completed** — The session took place and the professional has marked it as done.
- **cancelled** — Either the professional or the client cancelled the appointment before it happened. The time slot becomes available again.
- **no_show** — The professional marked that the client did not appear for the appointment.

Transitions: a pending_confirmation appointment can move to confirmed or rejected. A confirmed appointment can move to completed, cancelled, or no_show. Cancelled, rejected, completed, and no_show are terminal states.

In parallel, each appointment has a payment status that tracks separately from the appointment status. The possible payment statuses are: **none** (no payment tracked), **authorized** (the professional confirmed the appointment and payment is pending), **captured** (the professional marked the appointment as paid), and **refunded** (the appointment was rejected and any authorization reversed).

---

## Features for professionals

Odys provides the following features to professionals, depending on their subscription plan:

**Scheduling and booking management:**
- A public booking page at `odys.com.br/p/[slug]` with an interactive calendar and available time slots.
- Manual or automatic appointment confirmation, configurable per professional.
- Appointment actions: confirm, reject, cancel, mark as paid, mark as completed, or mark as no-show.
- Recurring appointments (weekly, biweekly, or twice-weekly patterns) — available on the Pro plan and above.

**Automated WhatsApp communication:**
- Instant notification to the professional when a client requests an appointment.
- Automatic confirmation or rejection message sent to the client.
- 24-hour reminder sent automatically before each confirmed session.
- 1-hour reminder sent automatically before each confirmed session.
- Cancellation, completion, and no-show notifications sent to the client.
- Payment confirmation messages.
- All messages are sent from the professional's own WhatsApp number.

**Dashboard:**
- Today's view showing appointments with real-time status.
- Client list with full session history, private notes, and messaging history.
- Direct messaging system between professional and client (Pro plan).
- Financial reports showing revenue by period, completed sessions, and no-shows (Pro plan).
- Real-time notification bell for in-app alerts.
- AI assistant for natural-language questions about the practice (Pro plan).

**Settings:**
- Public profile including photo, bio, and welcome message.
- Weekly availability configured by day of the week and time range.
- Session duration and price configuration.
- Payment policy selection (upfront, percentage, or post-session).
- PIX key registration for receiving payments from clients.

---

## Features for clients

Odys provides the following features to clients of professionals:

- Self-service booking through the professional's public page — no account is required to book.
- A client portal at `odys.com.br/c` where clients with accounts can view their appointment history, check status, and cancel upcoming appointments.
- Post-session rating and review: clients can rate their appointment from 1 to 5 stars and leave a written comment after the professional marks the session as completed.
- Ability to follow favorite professionals and receive updates.
- In-app messaging with professionals (for clients of Pro-plan professionals).
- Appointment history with full details including date, time, status, and professional name.

A client does not need an account to book an appointment, but if they create an account later, the professional's confirmation WhatsApp message includes a pre-filled registration link.

---

## Plans and pricing

Odys offers four subscription plans. All prices are in Brazilian reais (BRL) per month.

**Free plan (R$0 per month):**
- Limited to 10 clients and 20 appointments per month.
- Includes the public booking page and PIX integration.
- Does not include WhatsApp reminders, recurring appointments, messaging, private notes, financial reports, or the AI assistant.

**Basic plan (R$39 per month):**
- Unlimited clients and unlimited appointments per month.
- Includes all Free plan features plus: WhatsApp reminders (24-hour and 1-hour), and automatic confirmation.
- Does not include recurring appointments, messaging, private notes, financial reports, or the AI assistant.

**Pro plan (R$79 per month):**
- Unlimited clients and unlimited appointments.
- Includes all Basic plan features plus: recurring appointments, client profiles with private notes, in-app messaging with clients, financial reports, and the AI assistant.

**Premium plan (R$149 per month):**
- Includes all Pro plan features.
- The differentiator is support for multiple professionals under a single account (marked as coming soon).

**14-day Pro trial:** New professionals receive a 14-day free trial of the Pro plan on signup. During the trial, the `effectivePlan()` function returns "pro" regardless of the actual stored plan, so the user gets access to all Pro features. When the trial ends, the plan reverts to whatever is stored (free by default). Trial expiration emails are sent automatically at 3 days remaining and 1 day remaining.

Plan limits are enforced server-side in the code at `src/lib/plan-guard.ts` via the `canUseFeature()` function. Plan changes happen exclusively through Stripe webhooks — there is no client-side path to upgrade or downgrade a plan directly.

---

## How does booking an appointment work?

The booking endpoint is `POST /api/booking`. When a client submits a booking through the public page, the server executes the following steps in order:

1. The request is rate-limited at 5 requests per IP every 10 minutes to prevent abuse.
2. The request body is validated with Zod. Required fields are the professional's slug, the start time (as an ISO datetime), the client's name, and the client's phone number. The client's email is optional.
3. The professional record is loaded by slug.
4. The professional's plan limits are checked. If the plan has limits (Free plan), the server counts the existing clients and monthly appointments for that professional and rejects the booking if any limit is exceeded. Existing clients (matched by phone) are allowed to book even at the client cap.
5. The server performs an overlap check against existing appointments. It queries for any appointment belonging to the same professional where the existing appointment's start is before the proposed end and the existing appointment's end is after the proposed start, excluding appointments with status "rejected" or "cancelled." If any overlap is found, the server returns HTTP 409 Conflict with a message asking the client to choose another time.
6. The server upserts the client record. It looks for an existing client under the same professional by matching phone number or email; if found, it reuses the record (and updates the email if it was empty before and is now provided). If not found, a new client record is created.
7. The appointment is inserted into the database with status "pending_confirmation," unless the professional has enabled `autoConfirm`, in which case it is inserted as "confirmed."
8. Three side-effects are fired: an in-app notification for the professional is created (awaited), a WhatsApp message is sent to the professional's number (fire-and-forget), and an email notification is sent to the professional's email (fire-and-forget). The WhatsApp and email failures never block the HTTP response.

---

## How does the AI assistant work?

The AI assistant is available in the professional dashboard at `/dashboard/assistant` and is restricted to Pro and Premium plan subscribers. It allows the professional to ask natural-language questions in Portuguese about their appointments, clients, no-show rate, and revenue, and receive accurate answers based on real data from their account.

The assistant is implemented at `src/app/api/ai/chat/route.ts` using the Groq SDK. The model used is `llama-3.3-70b-versatile`. The flow is:

1. The server verifies the user is authenticated and has an associated professional profile.
2. The server checks if the professional's plan allows the AI assistant feature via `canUseFeature(plan, "assistant", trialEndsAt)`. If not, it returns 403 Forbidden.
3. The server sends the user's message to Groq with a list of three registered tools available to the model.
4. Groq decides whether to call one of the tools based on the user's question, using the `tool_choice: "auto"` setting.
5. If a tool is called, the server executes the corresponding database query scoped to the current professional's ID, then sends the result back to Groq for a natural-language response.
6. The final response is returned to the user.

The three available tools are:
- **`get_stats`** — Returns a global summary and a month-by-month breakdown of the professional's performance over the last 6 months, including total appointments, completed sessions, no-shows, cancellations, no-show rate, and revenue in Brazilian reais.
- **`get_upcoming`** — Returns the professional's confirmed appointments for the next 7 days, up to 20 rows, with client name, date, time, and status.
- **`get_no_show_clients`** — Returns a ranking of the top 10 clients by absolute number of no-shows in the last 6 months, with total appointments, no-shows, and individual no-show rate.

The AI assistant has layered safety guardrails:
- **Plan check** before any call to Groq, so the system does not spend tokens on unauthorized users.
- **Tenant isolation** enforced at the SQL layer: every tool query is scoped to the authenticated professional's ID, so the model can never access another professional's data.
- **Deterministic math**: revenue is calculated inside the tool (`completed_count × session_price`), not by the model, to avoid numerical hallucinations.
- **System prompt rules**: the prompt instructs the model to always use tools, never invent numbers, respond in Portuguese, format currency values in BRL, and follow a specific output structure for common intents.
- **Unknown tool handling**: if the model ever attempts to call a tool that does not exist, the server returns an error object instead of throwing.

---

## How does WhatsApp integration work?

Odys sends WhatsApp messages through Evolution API, an open-source self-hosted wrapper around WhatsApp Web. The Evolution API server is hosted on Railway using the Docker image `tiagorcfortunato/evolution-api-odys` and uses a separate Supabase Postgres database for its own schema.

Each professional connects their personal or business WhatsApp account to Odys by scanning a QR code once during setup. After that, every outgoing message from Odys is sent through Evolution API and appears on the client's end as if the professional had typed and sent it personally.

The sending logic lives in `src/lib/whatsapp.ts`. The `sendWhatsApp()` function never throws an error — on failure it catches, logs, and returns `false`, so WhatsApp delivery never blocks the core user flow. A 1200-millisecond delay is included in every request to make delivery feel more human and avoid rate triggers from WhatsApp itself. Phone numbers are normalized before sending: if the number starts with 55 and has at least 12 digits, it is kept as-is; if it has 12 or more digits and starts with a non-55 country code, it is kept as-is; otherwise 55 is prepended.

Odys uses approximately 19 pre-formatted WhatsApp message templates, each implemented as a named function in `src/lib/whatsapp.ts`. The templates cover booking requests, booking confirmations, booking rejections, cancellations by professional and by client, 24-hour reminders, 1-hour reminders, professional-side receipts, registration invitations, payment confirmations, session completion notifications, no-show notifications, and new-message alerts for both sides of the conversation. Message templates are never written inline in API routes — they always come from `whatsapp.ts`.

---

## WhatsApp reliability — the watchdog system

Because Evolution API relies on a WhatsApp Web session, that session can occasionally drop. To catch these drops early, Odys runs a WhatsApp watchdog as a scheduled job at `GET /api/cron/whatsapp-watchdog`. The watchdog runs every day at 09:00 (configured in `vercel.json`).

The watchdog:
1. Calls the Evolution API endpoint `/instance/fetchInstances` to check the current connection status.
2. If the status is `"open"`, it returns `{ ok: true }` and does nothing else.
3. If the status is anything other than `"open"`, it calls `/instance/connect/{instance}` to force a reconnection.
4. It waits 10 seconds for the connection to re-establish.
5. It queries the connection status again and returns a report showing the status before and after the reconnection attempt.

The watchdog is authenticated via either an `x-cron-secret` header or an `Authorization: Bearer <CRON_SECRET>` header, supporting both Vercel's native cron mechanism and manual debugging calls.

---

## How do WhatsApp reminders work?

The reminders cron runs every day at 08:00 at `GET /api/cron/reminders`. It sends two types of reminders and also sends trial expiration emails.

**24-hour reminders:** The cron queries for all appointments where the status is "confirmed," the `reminder_sent_24h` flag is `false`, and the appointment's start time falls between 23 hours and 25 hours from now. The 2-hour window is intentional: it ensures that every confirmed appointment falls into exactly one daily run of the cron, and it adds resilience if a previous run was missed. For each matching appointment, the cron re-checks the professional's plan eligibility for reminders (in case the plan changed since the appointment was booked), sends the WhatsApp reminder, and then bulk-updates the `reminder_sent_24h` flag to `true` for all successfully-sent appointments.

**1-hour reminders:** Same pattern as the 24-hour reminders, but with a window of 50 to 70 minutes from now and using the `reminder_sent_1h` flag.

**Trial expiration emails:** The cron also scans professionals whose trial has not yet ended. For any professional whose trial ends in exactly 3 days or exactly 1 day, it sends an automated email through Resend to remind them.

Reminder sending requires the professional to be on the Basic plan or higher. Free-plan professionals do not get automated WhatsApp reminders.

---

## How does payment work in Odys?

Odys supports two layers of payment:

**1. The professional's subscription to Odys.** Professionals pay for their Odys plan through Stripe. The checkout flow is handled at `POST /api/stripe/checkout`, which creates a Stripe Checkout Session in subscription mode with the selected plan's price ID. If the professional is currently in their 14-day Pro trial and is purchasing the Pro plan, the checkout session respects the existing trial end date and does not require a payment method upfront. After payment, Stripe sends a webhook to `POST /api/stripe/webhook`, which updates the professional's plan, Stripe customer ID, and subscription ID in the database. The webhook also handles `customer.subscription.updated` events (to handle upgrades and downgrades made through the Stripe Customer Portal) and `customer.subscription.deleted` events (which reset the professional to the Free plan). The webhook signature is verified using `stripe.webhooks.constructEvent` to prevent tampering — all plan changes happen only through this signed webhook path.

**2. Payments from clients to professionals.** Odys integrates with PIX, Brazil's instant-payment rail. Each professional can register their PIX key (which can be a phone number, email, CPF, CNPJ, or random key). When a client books an appointment with a professional who requires upfront payment, Odys can display a PIX QR code that the client scans to pay directly to the professional. The PIX QR code is generated entirely on the Odys server using the `buildPixPayload()` function in `src/lib/pix.ts`, which implements Banco Central's EMV BR Code specification with a CRC16/CCITT-FALSE checksum. Payment status is tracked on each appointment (`none`, `authorized`, `captured`, `refunded`), but the professional marks payment manually — Odys does not currently reconcile PIX payments automatically with bank statements.

---

## What payment methods does Odys accept for subscriptions?

For the professional's monthly Odys subscription, payment is handled by Stripe and accepts credit cards. The checkout page is hosted by Stripe and localized to Brazilian Portuguese (`pt-BR`). The professional manages their subscription (upgrades, downgrades, cancellations) through the Stripe Customer Portal.

For payments between clients and professionals (the actual service payments), Odys uses PIX, which is free for the professional and does not involve any intermediary fees. The professional receives the payment directly in their own bank account linked to their PIX key.

---

## How does authentication work in Odys?

Odys uses Supabase Auth for user authentication. Both professionals and clients can create an account using either email and password or Google OAuth (social sign-in). All authentication is handled via the `@supabase/ssr` library, which bridges Supabase sessions with Next.js server-side rendering through cookies.

Every authenticated API route in Odys starts by calling `getUser()`, a helper in `src/lib/api.ts` that reads the Supabase session cookie, asks Supabase for the current user, and returns the user object or `null`. Protected routes then call `getProfessional(userId)` to fetch the professional record associated with that user, if one exists.

Authorization (who can do what) is enforced per-route. For example, the appointment PATCH endpoint loads the appointment, the professional, and the client, then derives two flags: `isProfessional` (true if the current user owns the professional record) and `isClient` (true if the current user owns the client record). Each action then gates on one or both flags: cancel is allowed for both sides, while marking paid/completed/no-show is restricted to the professional.

---

## How does the professional sign up for Odys?

A new professional goes through the following onboarding flow:

1. The professional creates a Supabase account via email/password or Google OAuth on the registration page.
2. The professional is redirected to the onboarding wizard at `/onboarding`, where they fill in their name, phone number, profession, bio (optional), session duration in minutes, session price in cents, and weekly availability (days of the week and time ranges).
3. On submission, the onboarding API at `POST /api/onboarding` generates a unique URL slug from the professional's name (by lowercasing, removing accents, replacing spaces with dashes, and appending a numeric suffix if the slug is already taken). The rate limit for onboarding is 3 requests per hour per IP.
4. A new professional record is inserted into the database with default values, and the availability records are created in a separate table.
5. Supabase user metadata is updated to mark the user as a `"professional"` type.
6. The professional is redirected to the dashboard and can immediately activate their 14-day Pro trial if they wish.

The onboarding endpoint is idempotent: if a professional record already exists for the user, it is returned without creating a new one.

---

## How does the 14-day Pro trial work?

New professionals can activate a free 14-day Pro trial through the `POST /api/trial` endpoint. The trial can only be activated once per professional (the server rejects the request if `trialEndsAt` is already set). On activation, the `trialEndsAt` field on the professional record is set to 14 days from the current date (the constant `TRIAL_DAYS` is defined in `src/lib/constants.ts`).

While the trial is active, the `effectivePlan()` function in `src/lib/plan-guard.ts` returns `"pro"` for every plan check, so the professional gets access to all Pro-level features regardless of their actual stored plan. When the trial ends, `effectivePlan()` returns the stored plan, which is typically `"free"` unless the professional has already subscribed to a paid plan during the trial. Trial expiration emails are sent automatically by the daily reminders cron at 3 days remaining and 1 day remaining.

The trial is also integrated with Stripe checkout: if a professional is still in their trial and purchases the Pro plan, the checkout session is created with `trial_end` set to the existing trial end date, and `payment_method_collection: "if_required"`, so the professional does not need to enter a card until the trial ends.

---

## Recurring appointments — how do they work?

Recurring appointments are available on the Pro and Premium plans. A professional can set up a recurring schedule for a client with one of three frequencies:

- **weekly** — every week on a specified day of the week.
- **biweekly** — every two weeks on a specified day of the week.
- **twice_weekly** — twice a week on two specified days of the week.

When a recurring schedule is created through `POST /api/recurring`, Odys immediately generates concrete appointments for the next 8 weeks (the constant `RECURRING_WEEKS_AHEAD` in `src/lib/constants.ts`). Each generated appointment is inserted with status `"confirmed"` and is linked back to the recurring schedule via `recurring_schedule_id`. Generating real appointments up-front (rather than computing them on the fly) means they show up normally in the calendar, participate in the overlap check, and receive reminders like any other appointment.

When a recurring schedule is deleted through `DELETE /api/recurring`, the schedule is marked as inactive (`active = false`), but any already-generated future appointments remain in the calendar. The professional can cancel each of those individually if they wish.

---

## Messaging between professionals and clients

Odys provides an in-app messaging system available on the Pro and Premium plans. Messages are exchanged between a professional and one of their clients. Messages support three types: plain text, link, and PDF. Each message is stored in the `messages` table with a `sender` field indicating whether the message came from the professional or the client, and a `readAt` timestamp to track read status.

When the professional sends a message to a client, Odys also sends a WhatsApp notification to the client's phone with a preview of the message content and a link back to the client portal at `/c`. When the client sends a message to the professional, a corresponding WhatsApp notification is sent to the professional's phone with a link to the dashboard messages view.

Access to the messaging feature is gated by the `canUseFeature(plan, "messages", trialEndsAt)` check. The `GET /api/messages` endpoint returns the conversation between a specific professional-client pair, scoped so that each side can only access their own conversations.

---

## Reviews and ratings

After a professional marks an appointment as completed, the client is invited (via WhatsApp and via the client portal) to leave a review. Reviews are submitted through the `POST /api/reviews` endpoint and stored in the `reviews` table. Each review is linked to an appointment and includes:

- A rating from 1 to 5 stars.
- An optional written comment.

Each appointment can have at most one review (enforced by a unique constraint on `appointment_id`). Reviews are displayed on the professional's public booking page and contribute to the professional's aggregate rating shown in the `/explore` discovery directory.

---

## The client portal

Clients who have created an Odys account can access the client portal at `odys.com.br/c`. The portal provides:

- A list of all their appointments (past and upcoming) across all professionals they have booked with.
- The ability to cancel upcoming appointments that are in `pending_confirmation` or `confirmed` status.
- A list of professionals they follow.
- A messaging interface for conversations with professionals (when the professional has the Pro plan).
- Their profile page where they can update their name, phone, email, and avatar.

Clients who do not have an account can still book appointments (using only their name, phone, and optional email), but they do not have a portal to view their history. Every confirmation WhatsApp message sent to such clients includes a registration link with their data pre-filled, encouraging them to create an account.

---

## Professional discovery — the explore page

The `/explore` page is a public directory where anyone can search for professionals by profession category or by name. It lists all active professionals with their profile photo, name, profession, bio preview, and aggregate rating. Professionals are grouped by the six profession categories (Saúde, Fitness, Bem-estar, Beleza, Educação, Criativo). Each listing links to the professional's public booking page at `/p/[slug]`.

---

## Rate limiting and security

Odys uses Upstash Redis for rate limiting to prevent abuse. There are three separate sliding-window rate limiters, each with a distinct Redis key prefix so they do not collide:

- **Booking limiter** (`rl:booking`) — 5 requests per IP address every 10 minutes, applied to the public booking endpoint.
- **API limiter** (`rl:api`) — 60 requests per IP address per minute, applied to general API endpoints like messaging.
- **Onboarding limiter** (`rl:onboarding`) — 3 requests per IP address per hour, applied to the onboarding endpoint to prevent automated account creation.

The client IP address is extracted from the `x-forwarded-for` HTTP header (the first value in the comma-separated list), with a fallback to `"anonymous"` if the header is missing. When a rate limit is exceeded, the API returns HTTP 429 Too Many Requests with a friendly error message.

Other security measures in Odys include:
- All API routes validate input with Zod before touching the database.
- Internal errors are never exposed to the client — only logged server-side through Sentry.
- Stripe webhooks are verified using the Stripe signature header before processing.
- Plan upgrades and downgrades happen exclusively through Stripe webhooks, never from client requests.
- The Evolution API connection is protected by an API key stored in environment variables.
- CRON endpoints are protected by a shared secret (`CRON_SECRET`) that must match either an `x-cron-secret` header or an `Authorization: Bearer` header.

---

## LGPD compliance and privacy

Odys is designed to comply with the Brazilian General Data Protection Law (LGPD — Lei Geral de Proteção de Dados). Key privacy-related features include:

- A privacy policy page at `/privacidade` describing data collection, processing, and user rights.
- A terms of service page at `/termos`.
- A cookie consent banner that asks users to accept tracking cookies (for PostHog analytics) before any non-essential cookies are set.
- The ability for any user (professional or client) to delete their account entirely through the `DELETE /api/account` endpoint. When a professional deletes their account, all their data cascades: availability records, clients, client notes, recurring schedules, appointments, messages, follows, reviews, and notifications are all deleted automatically via foreign-key `ON DELETE CASCADE` rules in the database schema.
- Personal data is stored only in the Brazilian region (Supabase project located in South America).

---

## Key Technical Decisions — the "why" behind every choice

These are the reasons Tiago picked each major technology in Odys. Recruiters and engineers often ask "why X over Y?" — these are the answers.

**Why Next.js 16 App Router?** SSR for SEO on public booking pages and API routes in the same codebase — as a solo developer, Tiago did not want to own a separate backend. One deployable, one codebase.

**Why Drizzle ORM over Prisma?** Three reasons. First, Drizzle is lighter — no code generation step, no separate migration runner unless you want one. Second, type inference happens at the query level, so `db.select().from(appointments)` already has the right shape without a generated client getting out of sync. Third, Drizzle's query syntax is basically SQL-in-TypeScript, which lets Tiago drop to raw SQL via ```sql`` ``` for things like the `count(*) filter (where ...)` aggregation in the AI assistant's no-show query — that would be painful in Prisma.

**Why Supabase over self-hosted PostgreSQL?** Managed auth + PostgreSQL + storage from one vendor, and the pooled connection string works from serverless (Vercel).

**Why `prepare: false` on postgres-js?** Required for PgBouncer transaction mode, which Supabase's pooler uses. Prepared statements are per-connection state, so they break when PgBouncer rotates server connections between clients. Turning off prepared statements is the documented workaround.

**Why Evolution API (self-hosted) over WhatsApp Business API?** Messages send from the professional's real phone via WhatsApp Web — that is the actual product differentiator for Odys, because clients trust messages from the number they already know. WhatsApp Business API sends from a business account that clients do not recognize, and it is roughly 10× more expensive. Self-hosted Evolution API is what makes Odys "WhatsApp-first".

**Why Groq for the AI assistant?** Latency. Groq's LPU architecture gets `llama-3.3-70b-versatile` responses back in under a second for short contexts. Tool-calling chat feels instant. On OpenAI, the same model class would be noticeably slower for this chat-style workload.

**Why tool-calling with scoped SQL instead of embedding-based RAG for the AI assistant?** The assistant answers must cite real numbers (revenue, no-show counts, upcoming appointments). Structured SQL queries over structured data are the right answer for that — RAG over documents would hallucinate numbers. The AI model picks the tool, the tool runs scoped SQL, and the result goes back to the model to format the answer.

**Why Upstash Redis for rate limiting?** Serverless-friendly — it uses HTTP, not a TCP connection pool, so it works cleanly from Vercel's serverless functions. Cheap. Easy to have multiple isolated limiters with different prefixes.

**Why Zod for request validation?** "Parse, don't validate." The TypeScript type is derived from the schema, so runtime checks and compile-time checks can never drift apart. One source of truth for request shape.

**Why Stripe webhooks as the only plan-update path?** Client-trusted plan upgrades are a security smell. Stripe signs the event, Tiago's webhook verifies the signature, and only then the database gets updated. There is no client-side code path that can escalate a plan.

**Why Vercel cron over Inngest, Trigger.dev, or other workflow tools?** Odys has two daily cron jobs, no fan-out, no complex workflows. Vercel cron is simple, bundled, and free. Tiago would reach for Inngest only if he needed delayed actions or workflows.

**Why Sentry and PostHog separately?** They solve different problems. Sentry handles errors — stack traces, source maps, release tracking. PostHog handles product analytics — funnels, events, feature flags. Using one tool for both would be worse at each.

**Why postgres-js driver directly over `@supabase/supabase-js`?** Tiago wanted direct Drizzle queries with full type inference, not the PostgREST-based REST layer that `@supabase/supabase-js` provides for data access. PostgREST is great for quick prototyping; Drizzle is better for production query patterns.

**Why Resend over SendGrid or Postmark?** Developer experience — TypeScript SDK, good React Email compatibility, clean domain verification flow, and the free tier fits a solo launch.

**Why shadcn/ui + Tailwind v4 instead of a component library?** shadcn/ui gives you copy-paste components that Tiago owns in his own codebase, not a dependency he is stuck with. If he needs to change a Button, he edits the file directly — no overrides, no wrappers, no fighting a third-party API.

**Why fire-and-forget side effects for WhatsApp and email after booking?** The user clicked "confirm booking" — they need a fast 200 response. A WhatsApp send taking 2 seconds should not block that response. The in-app notification (which is the SLA-sensitive surface) IS awaited, but WhatsApp and email are fire-and-forget with `.catch` handlers.

**Why 19 WhatsApp templates as named functions instead of inline strings?** Single source of truth. Every message Odys sends is a function in `lib/whatsapp/templates.ts`. No typos, searchable, testable, and any copy change is one file and one commit.

---

## Technical stack

Odys is built on the following technology stack:

- **Framework:** Next.js 16.2.1 with the App Router, providing both server-side rendered pages and API routes in a single codebase.
- **Language:** TypeScript 5.
- **UI:** React 19.2.4 with Tailwind CSS v4, shadcn/ui components, and Base UI primitives.
- **Database:** Supabase PostgreSQL (managed).
- **ORM:** Drizzle ORM 0.45.2 using the `postgres-js` driver (configured with `prepare: false` for compatibility with Supabase's PgBouncer connection pooler).
- **Authentication:** Supabase Auth (email/password and Google OAuth).
- **WhatsApp:** Evolution API v2 (self-hosted on Railway).
- **Email:** Resend (transactional emails with custom HTML templates).
- **Payments:** Stripe for subscriptions, PIX for client-to-professional payments.
- **Rate limiting:** Upstash Redis with `@upstash/ratelimit`'s sliding-window algorithm.
- **Error monitoring:** Sentry.
- **Product analytics:** PostHog.
- **AI assistant:** Groq SDK 1.1.2, using the model `llama-3.3-70b-versatile`.
- **Request validation:** Zod 4.
- **Date arithmetic:** date-fns 4.
- **Hosting (app):** Vercel, with auto-deploy from the `main` branch.
- **Hosting (WhatsApp API):** Railway, running a Docker image.
- **CI/CD:** GitHub Actions, running TypeScript type-checking (`tsc --noEmit`), ESLint, and production build on every push and pull request.

---

## Database schema

Odys has 10 PostgreSQL tables, defined in `src/lib/db/schema.ts`:

1. **`professionals`** — The core account record for each professional. Contains the user ID (linked to Supabase Auth), name, URL slug, phone, email, profession, bio, avatar URL, session duration, session price, plan, payment type, payment percentage, PIX key type and value, Stripe customer ID and subscription ID, trial end date, welcome message, auto-confirm flag, active flag, and timestamps.
2. **`availability`** — Weekly working hours per professional. Each row represents one day of the week (0 for Sunday through 6 for Saturday) with a start time and end time.
3. **`clients`** — Client records per professional. Clients are owned by a single professional, can optionally be linked to a Supabase user ID, and are identified by name, phone, and optional email.
4. **`client_notes`** — Private notes that professionals keep about their clients, visible only to the professional (Pro plan feature).
5. **`recurring_schedules`** — Recurring appointment patterns with frequency, day(s) of the week, and time of day.
6. **`appointments`** — Individual booked sessions with start and end times, status, payment status, reminder-sent flags for 24h and 1h, optional link back to a recurring schedule, and optional notes.
7. **`messages`** — Chat messages between professionals and clients, with sender side (professional or client), type (text, link, or pdf), content, optional file URL, and read timestamp.
8. **`follows`** — Client-to-professional follow relationships.
9. **`reviews`** — Post-appointment ratings (1-5) and optional comments, one per appointment.
10. **`notifications`** — In-app notifications for both professionals and clients, typed (booking_request, booking_confirmed, reminder_24h, new_message, payment_captured, etc.) with a read flag.

Foreign keys between tables cascade on delete from `professionals`, so deleting a professional account cleanly removes all related data.

Indexes are defined on high-traffic columns, including `professional_id` on most tables, `user_id` on clients, `starts_at` and `status` on appointments, a composite `(professional_id, client_id)` index on messages, and `recipient_id` on notifications.

---

## API endpoints

Odys has approximately 20 API route handlers under `src/app/api`. The main ones are:

- `POST /api/onboarding` — Create a new professional profile during signup.
- `GET /api/booking` — Return a professional's profile, weekly availability, and existing appointments for a given date.
- `POST /api/booking` — Create a new appointment (public endpoint, rate-limited).
- `PATCH /api/appointments/[id]` — Update the status of an appointment. Actions include confirm, reject, cancel, paid, complete, and no_show.
- `GET /api/messages` — Fetch conversation messages (professional-side or client-side).
- `POST /api/messages` — Send a new message between professional and client.
- `POST /api/recurring` — Create a recurring schedule and generate the next 8 weeks of appointments.
- `DELETE /api/recurring` — Deactivate a recurring schedule.
- `GET /api/notifications` — List notifications for the current user.
- `PATCH /api/notifications` — Mark notifications as read.
- `POST /api/follows`, `DELETE /api/follows`, `GET /api/follows` — Manage client-to-professional follows.
- `POST /api/reviews` — Submit a post-appointment review.
- `POST /api/trial` — Activate the 14-day Pro trial.
- `POST /api/stripe/checkout` — Create a Stripe Checkout Session for a subscription purchase.
- `POST /api/stripe/webhook` — Receive and process Stripe subscription events.
- `GET /api/cron/reminders` — Scheduled job that sends WhatsApp reminders and trial expiration emails.
- `GET /api/cron/whatsapp-watchdog` — Scheduled job that checks and restores the WhatsApp connection.
- `POST /api/auth/register` — Register a new Supabase user.
- `POST /api/upload/avatar` — Upload a profile photo.
- `POST /api/client-profile` — Fetch the authenticated client's profile.
- `POST /api/clients/notes` — Create a private client note (Pro plan).
- `PATCH /api/settings` — Update the professional's settings (profile, availability, pricing, PIX key, welcome message, auto-confirm).
- `DELETE /api/account` — Delete the authenticated user's account and all associated data.

---

## Cron jobs and scheduled tasks

Odys runs two scheduled jobs, configured in `vercel.json`:

- **`/api/cron/reminders`** runs daily at 08:00 (cron expression `0 8 * * *`). It sends 24-hour WhatsApp reminders, 1-hour WhatsApp reminders, and trial expiration emails (at 3 days and 1 day remaining).
- **`/api/cron/whatsapp-watchdog`** runs daily at 09:00 (cron expression `0 9 * * *`). It checks the Evolution API connection status and automatically reconnects the WhatsApp instance if it has dropped.

Both cron endpoints are authenticated with the shared `CRON_SECRET` environment variable, accepting either an `x-cron-secret` header or an `Authorization: Bearer <secret>` header.

---

## Deployment and infrastructure

Odys is deployed as follows:

- **Application:** The Next.js app is hosted on Vercel. Every push to the `main` branch triggers an automatic production deployment. Preview deployments are created for pull requests.
- **Database:** PostgreSQL is hosted on Supabase. The database uses PgBouncer in transaction mode for connection pooling, which is why the `postgres-js` driver is configured with `prepare: false` — prepared statements do not work across the rotating connections that PgBouncer assigns.
- **Evolution API (WhatsApp):** Hosted on Railway using the Docker image `tiagorcfortunato/evolution-api-odys`. It uses a separate Supabase Postgres project (`odys-evolution`) with the `evolution_api` schema, connected via PgBouncer on port 6543.
- **Rate limiting:** Upstash Redis (serverless, fetch-based).
- **File storage:** Supabase Storage for profile photos and PDF attachments in messages.
- **Email delivery:** Resend with a verified `noreply@odys.com.br` sender.
- **Error monitoring:** Sentry with source maps uploaded on each build.
- **Product analytics:** PostHog.
- **Continuous Integration:** GitHub Actions runs `tsc --noEmit`, `npm run lint`, and `npm run build` on every push and pull request.

---

## Professions supported by Odys

Odys supports approximately 30 professions organized into 6 categories. The profession metadata lives in `src/lib/professions.ts` and each profession has a label, an emoji, a color scheme, and a category.

- **Saúde & Clínica:** Psicólogo(a), Fisioterapeuta, Nutricionista, Dentista, Terapeuta, Fonoaudiólogo(a).
- **Fitness & Movimento:** Personal Trainer, Instrutor(a) de Yoga, Instrutor(a) de Pilates, Instrutor(a) de Dança.
- **Bem-estar & Terapias:** Massoterapeuta, Acupunturista, Terapeuta Holístico(a), Osteopata.
- **Beleza & Estética:** Cabeleireiro(a), Barbeiro(a), Manicure / Pedicure, Esteticista, Maquiador(a), Tatuador(a), Designer de Sobrancelhas, Lash Designer.
- **Educação & Coaching:** Professor(a) Particular, Professor(a) de Música, Professor(a) de Idiomas, Coach / Mentor(a).
- **Criativo & Serviços:** Fotógrafo(a), Personal Stylist, Personal Organizer.

When a professional onboards, they pick one of these professions. The profession determines the emoji and color theme used on their public booking page and in the `/explore` directory, and it is used to group professionals in the discovery search.

---

## Dark mode and responsive design

Odys has a dark mode available on all pages, which the user can toggle via a theme button. The theme preference is persisted in localStorage and respects the user's operating system preference by default. Odys is fully responsive and mobile-first — every page works on mobile screens, and the booking flow is optimized for mobile because most clients in Brazil book from their phones.

---

## How does a professional cancel their Odys subscription?

A professional with a paid Odys subscription (Basic, Pro, or Premium) can cancel their subscription through the Stripe Customer Portal, which is accessible from the `/dashboard/plans` page. When the cancellation is processed, Stripe sends a `customer.subscription.deleted` webhook event to Odys, and the professional's plan is automatically reset to `"free"` in the database. Any existing data (clients, appointments, messages, reviews) is preserved, but features restricted to paid plans (reminders, messaging, AI assistant, etc.) become inaccessible until the professional upgrades again. If the professional also wants to delete their entire account and all data, they can do so separately through the account-deletion option in settings, which calls `DELETE /api/account`.

---

## Does Odys work outside Brazil?

Odys is designed and optimized specifically for the Brazilian market. The user interface is entirely in Portuguese. The payment integration for subscriptions uses Stripe with the `pt-BR` locale. Client-to-professional payments use PIX, which is a Brazilian instant-payment system and is not available in other countries. WhatsApp phone numbers are normalized with a Brazilian country code prefix (55) if not otherwise specified, although non-Brazilian numbers with explicit country codes are preserved. The professions catalog reflects the Brazilian service industry. While the underlying technology could support other markets, Odys does not currently serve users outside Brazil.

---

## How do I contact Odys support?

Users can contact Odys support through the email address displayed on the website. The platform is currently maintained by its solo founder, Tiago Fortunato. For account-specific issues, users should email from the same address they registered with. For general product questions, the landing page and help sections inside the dashboard cover most common questions. Support response times are not guaranteed by a formal SLA at this stage of the product.

---

## FAQ — common user questions

**Do clients need an account to book an appointment?**
No. Clients can book through the professional's public page using only their name, phone, and optional email. If they create an account later, their booking history is automatically linked by phone number match.

**Is there a free plan?**
Yes. The Free plan costs R$0 and supports up to 10 clients and 20 appointments per month. It includes the public booking page and PIX integration, but it does not include WhatsApp reminders or other advanced features.

**How long is the free trial?**
New professionals get a 14-day free trial of the Pro plan on signup. The trial gives full access to all Pro features. Trial expiration emails are sent automatically at 3 days and 1 day remaining.

**Does Odys send SMS reminders?**
No. Odys sends reminders through WhatsApp only, from the professional's own real phone number via Evolution API. SMS is not supported because WhatsApp penetration in Brazil is near-universal and SMS would add cost and complexity for negligible benefit.

**Can I use my own WhatsApp number?**
Yes — this is the core product differentiator. Each professional connects their own WhatsApp account to Odys by scanning a QR code, and every automated message is sent from that number.

**What happens if my WhatsApp disconnects?**
Odys runs a daily WhatsApp watchdog at 09:00 that checks the connection status and automatically reconnects if the session has dropped. If the reconnection fails, an error is logged and the professional should rescan the QR code.

**Can I have multiple locations or multiple professionals under one account?**
Multiple professionals under one account is planned for the Premium plan (R$149/month) but is not yet available. Each professional currently has their own Odys account and their own public booking page.

**How does Odys handle payments from clients?**
Odys integrates with PIX for instant Brazilian payments. The professional registers their PIX key, and Odys can display a PIX QR code to clients at booking time. Payment status is tracked on each appointment but marked manually by the professional — Odys does not automatically reconcile bank statements.

**Is Odys compliant with LGPD?**
Yes. Odys has a privacy policy and terms of service, a cookie consent banner for analytics, and a full account deletion flow that cascades all related data. Data is stored in South American Supabase regions.

**Can I export my data?**
Account deletion is available through `DELETE /api/account`. A formal data export feature is not currently provided but can be requested through support.

**Does Odys integrate with Google Calendar?**
Not currently. Odys maintains its own calendar view inside the dashboard and does not sync with external calendar systems.

**Is there a mobile app?**
Odys is a responsive web application that works on mobile browsers, but there is no native iOS or Android app. The mobile web experience is optimized for both professionals and clients.

**Which AI model powers the assistant?**
The AI assistant uses `llama-3.3-70b-versatile` via the Groq API. Groq is used specifically for its low inference latency, so responses feel instant.

**What languages does Odys support?**
Odys is currently available only in Brazilian Portuguese. All UI copy, email templates, WhatsApp messages, and the AI assistant respond in Portuguese.
