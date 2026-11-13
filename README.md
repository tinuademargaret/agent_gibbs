# Fieldnotes — personal flashcard study

A private Streamlit app for importing **your own** questions, answers and explanations, editing them, and building a daily review habit. No AI service, generated answers, or model key is used.

## Run locally

Python 3.12+ is required. From this project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.auth
```

The last command securely prompts for a password and prints an Argon2 hash. Paste that hash into `APP_PASSWORD_HASH` in `.env` (keep the whole hash). Your password is never stored. Then:

```sh
python -m jobs.migrate
streamlit run app.py
```

Open the local URL and sign in with your chosen password. `.env`, local databases and Streamlit secrets are ignored by Git. Local development uses SQLite; **production requires external PostgreSQL**. Set `APP_ENV=production` for hosted deployments. The default is production unless the local `.env` overrides it.

## Use it

1. Create a deck in **Import** or **My decks**.
2. Upload a text-based PDF, UTF-8 TXT/Markdown, or paste the example in `examples/study_notes.md`. Imports are limited to 20 MB and PDFs to 500 pages. PDF text extraction happens in memory; uploads are not written to disk.
3. Preview and correct each question, short answer and explanation. **Save preview edits** retains corrections without importing. You can remove rows or add manual draft rows. **Confirm import** saves approved cards. Exact question/answer/explanation duplicates within the deck are skipped unless you select Keep duplicates. Re-imports never overwrite cards.
4. In **My decks**, search, edit, move, archive or permanently delete cards. Deleting a card also deletes its review history; the UI requires confirmation. Original imported answer, explanation and source excerpt remain available after edits.
5. **Review** shows the question first. Reveal, rate, then explicitly advance. Misses remain visible until Next card. A missed card is revisited once and remains due tomorrow even after a successful retry. Incomplete or archived cards are excluded. Ratings persist immediately; an interrupted session's queue is not recovered.
6. **Settings** saves reminder time, timezone, email and opt-in in the database. The independent job reads them on every run. Export all stored data as JSON here.

### Parsing and scheduling

Supported labels: `Q:`, `Question:`, `A:`, `Answer:`, `Explanation:`, `Detailed explanation:`, `Reasoning:` and bold Markdown variants. Numbered questions and question headings are supported. Multiline paragraphs, bullets and fenced code are retained; boundary blank lines are trimmed. PDF layout reconstruction cannot guarantee the original typography. Numbered prose can be ambiguous: inspect the preview against the retained source. Scanned PDFs produce an OCR warning; OCR is not included.

Missing explanations are labelled **Needs explanation**. Missing answers also exclude cards from study. The app never supplies missing content. Consecutive successes schedule 1, 3, 7, 14, 30, 60, 120, then 180 days (capped). A miss resets the streak and schedules tomorrow. Due dates use the configured local timezone; changing timezone preserves saved calendar dates.

## Deploy to Streamlit Community Cloud

1. Create a private GitHub repository containing this directory's contents at its root. Do not upload `.env`, local databases, personal source files or exports.
2. Create an external PostgreSQL database (for example, Supabase). Choose a connection endpoint reachable from both Streamlit and GitHub Actions; require TLS using `?sslmode=require` in the URL. Back it up before schema changes.
3. In Streamlit Community Cloud, create an app from your repository and `app.py`. Select Python 3.12 or newer.
4. Add the following **TOML secrets** in the Streamlit dashboard (replace placeholders). Do not commit real values:

```toml
APP_ENV = "production"
DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/DB?sslmode=require"
APP_PASSWORD_HASH = "PASTE_ARGON2_HASH"
APP_URL = "https://YOUR-APP.streamlit.app"
EMAIL_TEST_MODE = "true"
RESEND_API_KEY = "YOUR_KEY"
EMAIL_FROM = "Fieldnotes <study@YOUR-VERIFIED-DOMAIN>"
DEFAULT_TIMEZONE = "Europe/London"
DEFAULT_REMINDER_TIME = "08:00"
```

5. Start the app, sign in, and verify an import, edit, review and reload. Alembic initializes/upgrades the database at application startup. The reminder job intentionally does not migrate the database.
6. Enable your database provider's backups. Redeploy the app and verify cards/settings still exist before relying on it.

This is a single-owner app. Every content page, edit and export requires the password. Password verification uses Argon2; a session-level delay discourages repeated failures, but it is not a distributed rate limiter. Use a strong unique password and restrict deployment access through the host where available. There are no signups or multi-tenant isolation guarantees.

## Configure independent email reminders

The Streamlit process is **not** the scheduler. `.github/workflows/review_reminders.yml` runs every 15 minutes on GitHub Actions and can also be run manually. It must be present on the repository's default branch, with Actions enabled. GitHub schedules are best effort and can be delayed or disabled after repository inactivity.

1. Set up Resend, verify a sender domain, and obtain an API key. Provider plans and GitHub Actions quotas may incur charges; check your accounts before enabling recurring delivery.
2. Add repository Actions secrets: `DATABASE_URL`, `RESEND_API_KEY`, `EMAIL_FROM`, `APP_URL`. These are separate from Streamlit secrets. Both must use the **same external database**. The workflow explicitly uses production mode and real sending.
3. In app Settings, enter your email, tick the confirmation checkbox, choose a time and timezone, and enable reminders. Confirmation is the signed-in owner's explicit attestation; this MVP does not implement inbox-verification links. Changing the address requires confirmation again.
4. Leave `EMAIL_TEST_MODE=true` initially. The test button performs a dry run and does not consume the daily reminder slot. Local job test:

```sh
python -m jobs.send_reminders
```

5. Set `EMAIL_TEST_MODE="false"` in Streamlit secrets to enable its real test-email button. Click **Send test email** and check your inbox. Provider acceptance is not proof of inbox delivery. No real delivery has been verified as part of this local implementation.
6. Run the Actions workflow manually after the selected time and inspect both the job status and Settings delivery log. Change the time from 08:00 to 10:30, then 07:45; saved settings take effect without redeployment.

Any HH:MM time can be selected. Daytime reminders accept runs from the selected minute until three hours later, but never at/after 22:00. Explicitly selected times from 22:00 receive a narrower 30-minute window. Neither window spills into the next local date, so a selection near midnight may be missed if the scheduler is delayed. Only-due mode skips an empty day. Selecting a future time postpones that day's unsent reminder. Once sent, further time changes cannot trigger a second daily reminder.

A unique `(user_id, local_date)` database record plus Resend's idempotency key suppresses retries and concurrent sends. The payload is saved before sending and kept identical across retries, including after a timeout; this means a pending retry uses its original recipient and due count even if settings change. Disabling reminders stops retries. The three-hour window is shorter than Resend's 24-hour idempotency retention. Failures are recorded with safe messages and retried during eligible runs; test emails are intentionally separate from daily emails.

## Test and maintain

```sh
python -m pytest -q
```

Tests create disposable SQLite databases and synthetic PDFs. They cover extraction, source fidelity, malformed/scanned inputs, duplicates, persistence, review intervals and retry behaviour, reminder changes, winter/summer times, failure retries, idempotency, authentication gating, and an actual Streamlit AppTest import/review/settings flow. No test sends email. Hosted PostgreSQL and real provider delivery require deployment verification.

Schema history is in `migrations/versions`. `migrations/initial_schema.py` is a frozen initial model snapshot: leave it unchanged and add a new Alembic revision for future changes. `python -m jobs.migrate` applies migrations. Take a PostgreSQL backup before upgrades. JSON exports contain all data for inspection/portability, but there is no JSON restore UI yet; use database-native backups for restoration.

Troubleshooting:

- **Setup/login page:** set a complete Argon2 `APP_PASSWORD_HASH`; generate it with `python -m src.auth`.
- **Database unavailable:** check the URL, TLS, credentials, networking and provider availability. Do not paste credential-bearing URLs into logs/issues.
- **No cards due:** check drafts, archived state, timezone and due dates; use Study all to review early.
- **Missing emails:** check opt-in, confirmation, saved time, three-hour cutoff, due-only preference, test mode, sender verification, Actions status, spam folder and delivery log. Import and review do not require email credentials.
- **Scanned PDF:** export text with your own OCR tool and import the result. Review all extracted content before saving.

Relevant provider documentation: [Streamlit app testing](https://docs.streamlit.io/develop/api-reference/app-testing) and [Resend idempotency keys](https://resend.com/changelog/idempotency-keys).
