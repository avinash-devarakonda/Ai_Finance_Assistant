# Finora — Intelligent Personal Finance

A full-stack, AI-assisted personal finance workspace built for a B.Tech final-year project.
Track income and expenses, let a trained classifier categorise spending, set category
budgets, generate rule-based insights, forecast next month's expenses, chat with a
data-grounded assistant, and export monthly reports as CSV or PDF.

The application is **fully functional**, not a static mock-up. Every dashboard number,
chart, budget utilisation, insight, forecast and report is computed from the signed-in
user's own database records. The only bundled examples are the reproducible synthetic
datasets used to train and evaluate the ML models.

---

## Table of contents

1. [Feature highlights](#feature-highlights)
2. [Architecture](#architecture)
3. [Technology stack](#technology-stack)
4. [Project structure](#project-structure)
5. [Quick start (MySQL)](#quick-start-mysql)
6. [SQLite development fallback](#sqlite-development-fallback)
7. [Demo account](#demo-account)
8. [Machine learning](#machine-learning)
9. [REST API reference](#rest-api-reference)
10. [Datasets and retraining](#datasets-and-retraining)
11. [Jupyter notebooks](#jupyter-notebooks)
12. [Testing](#testing)
13. [Production build](#production-build)
14. [Security and data isolation](#security-and-data-isolation)
15. [Troubleshooting](#troubleshooting)
16. [Limitations and academic notes](#limitations-and-academic-notes)

---

## Feature highlights

| Area | What works |
| --- | --- |
| **Authentication** | Register, login, logout, JWT bearer tokens, password hashing, token revocation, protected client routes |
| **Transactions** | Create, read, update, delete; search, filter by type/category/date, sort, pagination; income and expense categories |
| **AI categorisation** | TF-IDF + amount-bucket classifier predicts one of 8 expense categories; confidence and alternatives shown; user corrections stored |
| **Dashboard** | Live KPIs, comparisons, 12-month cash-flow chart, category pie, weekly spending, budget utilisation, top categories/merchants, recent transactions, custom date ranges |
| **Budgets** | Monthly category limits, actual spend derived from transactions, utilisation bars, status thresholds, unbudgeted spending |
| **Insights** | Transparent rule-based insights from real month-over-month, budget, savings and forecast signals; skipped when evidence is missing |
| **Forecasting** | Linear Regression vs Random Forest evaluated per target; user forecasts blend personal history with the trained seasonal model; explicit insufficient-data messages |
| **Assistant** | Rule-based chatbot that answers only from the authenticated user's records; refuses investment/tax advice; suggestion chips and disclaimer |
| **Reports** | Month picker, summary, six-month trend, category breakdown, budget table, forecast card, transaction list, CSV and PDF download |
| **UX** | Responsive SaaS layout, sidebar, light/dark mode, rounded cards, skeleton/loading states, empty states, toasts, 404 page |
| **Deliverables** | Datasets, MySQL schema, trained `.pkl` bundles, metrics JSON, confusion-matrix and validation plots, notebooks, smoke tests |

---

## Architecture

```
┌─────────────────────────────┐        HTTPS / JSON        ┌──────────────────────────────┐
│  React 18 + Vite frontend   │  ───────────────────────▶  │  Flask REST API (JWT guard)  │
│  Tailwind · Recharts        │  ◀───────────────────────  │  Blueprints + services       │
│  React Router · Lucide      │        CSV / PDF           │  ├─ auth / transactions      │
└─────────────────────────────┘                            │  ├─ dashboard / budgets      │
                                                           │  ├─ insights / chatbot       │
┌─────────────────────────────┐                            │  ├─ ML predictions           │
│  Joblib model bundles       │  ◀── loaded once ────────  │  └─ reports / exports        │
│  classifier · forecaster    │                            └──────────────┬───────────────┘
└─────────────────────────────┘                                           │
                                                           ┌──────────────▼───────────────┐
                                                           │  MySQL 8 (default)           │
                                                           │  users · transactions        │
                                                           │  budgets · predictions       │
                                                           │  insights                    │
                                                           │  (SQLite dev/test fallback)  │
                                                           └──────────────────────────────┘
```

Request flow:

1. The React client sends `Authorization: Bearer <JWT>` with every API call.
2. A global Flask `before_request` guard authenticates all `/api/*` routes except
   health, register and login.
3. Route modules validate input and delegate to service modules.
4. Services run user-scoped SQL, call the ML services when needed, and return JSON.
5. The frontend renders only what the API returns — there are no hardcoded statistics.

---

## Technology stack

| Layer | Tools |
| --- | --- |
| Frontend | React 18, Vite 6, React Router 6, Tailwind CSS 3, Recharts 2, Lucide React |
| Backend | Python 3.11+, Flask 3, flask-cors, PyJWT, Werkzeug password hashing |
| Database | MySQL 8 (production/default), PyMySQL, raw parameterised SQL; SQLite 3 for automated tests/local fallback |
| Machine learning | scikit-learn, pandas, NumPy, Joblib, Matplotlib |
| Reporting | ReportLab (PDF), Python `csv` (CSV) |
| Notebooks | Jupyter / nbformat |
| Testing | Flask test client smoke suite with temporary SQLite database |

---

## Project structure

```
Finora/
├── backend/
│   ├── app.py                     # Flask app factory, auth guard, static frontend serving
│   ├── config.py                  # Environment configuration
│   ├── database.py                # MySQL/SQLite connection layer
│   ├── init_db.py                 # Create MySQL database or SQLite schema
│   ├── seed_demo.py               # Deterministic demo account + 8 months of data
│   ├── test_api.py                # End-to-end API smoke tests
│   ├── requirements.txt
│   ├── ml/
│   │   ├── feature_utils.py
│   │   ├── train_classifier.py
│   │   ├── train_forecasting.py
│   │   ├── expense_classifier.pkl
│   │   ├── expense_forecasting.pkl
│   │   ├── classifier_metrics.json
│   │   ├── forecasting_metrics.json
│   │   ├── confusion_matrix.png
│   │   └── forecast_validation.png
│   ├── models/
│   │   └── serializers.py
│   ├── routes/
│   │   ├── auth.py
│   │   ├── transactions.py
│   │   ├── dashboard.py
│   │   ├── budgets.py
│   │   ├── ml.py
│   │   ├── insights.py
│   │   ├── chatbot.py
│   │   └── reports.py
│   ├── services/
│   │   ├── classifier_service.py
│   │   ├── forecast_service.py
│   │   ├── budget_service.py
│   │   ├── dashboard_service.py
│   │   ├── insights_service.py
│   │   ├── chatbot_service.py
│   │   └── report_service.py
│   └── utils/
│       ├── auth.py
│       ├── dates.py
│       ├── formatters.py
│       ├── responses.py
│       └── validators.py
├── database/
│   └── schema.sql                 # MySQL schema (users, transactions, budgets, predictions, insights)
├── datasets/
│   ├── generate_datasets.py       # Deterministic synthetic-data generator (seed 42)
│   ├── expense_transactions.csv
│   ├── monthly_expenses.csv
│   ├── budget_data.csv
│   └── financial_insights.csv
├── notebooks/
│   ├── 01_dataset_exploration.ipynb
│   ├── 02_expense_classifier.ipynb
│   └── 03_expense_forecasting.ipynb
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   ├── index.html
│   └── src/
│       ├── main.jsx
│       ├── App.jsx
│       ├── components/
│       ├── context/
│       ├── hooks/
│       ├── layouts/
│       ├── pages/
│       ├── services/
│       └── utils/
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

---

## Quick start (MySQL)

### 1. Prerequisites

- Python **3.11+**
- Node.js **18+** and npm
- MySQL **8.x** running locally (or any reachable MySQL server)
- Git is optional; the project runs directly from its folder

### 2. Install dependencies

```bash
# From the project root
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

```bash
cd frontend
npm install
cd ..
```

### 3. Configure the environment

```bash
# Windows
copy .env.example .env
# macOS / Linux
cp .env.example .env
```

Edit `.env` and set at minimum:

```ini
FLASK_ENV=development
SECRET_KEY=replace-with-a-long-random-secret
JWT_SECRET=replace-with-a-different-long-random-secret
CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173

DB_ENGINE=mysql
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=your_mysql_password
DB_NAME=finora
```

### 4. Create the database

Either run the SQL schema directly:

```bash
mysql -u root -p < database/schema.sql
```

or let the helper create the database and tables:

```bash
python backend/init_db.py
```

`init_db.py` uses the MySQL credentials from `.env`. The SQL file remains the
canonical schema.

### 5. Seed the demo account (recommended)

```bash
python backend/seed_demo.py
```

This creates **eight months** of deterministic transactions (ending in the current
month) and category budgets for the demo user. It is safe to re-run: it resets only
that user's records.

> The demo account is required for the "Fill demo account credentials" shortcut on
> the login page. You can also register a fresh account and add your own data.

### 6. Start the backend

```bash
python backend/app.py
```

- API: <http://localhost:5000>
- Health check: <http://localhost:5000/api/health>

### 7. Start the frontend

In a second terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. Vite proxies `/api` to `http://localhost:5000`, so
no extra frontend environment variable is needed for local development.

---

## SQLite development fallback

MySQL is the delivered/default target. For machines without MySQL — or for quick
marking and automated tests — the backend supports an explicit SQLite mode:

```bash
# Windows PowerShell
$env:DB_ENGINE="sqlite"
$env:SQLITE_PATH="backend/finora.sqlite3"
python backend/init_db.py
python backend/seed_demo.py
python backend/app.py
```

```bash
# macOS / Linux
DB_ENGINE=sqlite SQLITE_PATH=backend/finora.sqlite3 python backend/init_db.py
DB_ENGINE=sqlite SQLITE_PATH=backend/finora.sqlite3 python backend/seed_demo.py
DB_ENGINE=sqlite SQLITE_PATH=backend/finora.sqlite3 python backend/app.py
```

Keep `DB_ENGINE=mysql` in `.env` for the submitted/production configuration. The
SQLite schema is created automatically by `create_app()` when that mode is active.

---

## Demo account

After running `python backend/seed_demo.py`:

| Field | Value |
| --- | --- |
| Email | `demo@finora.local` |
| Password | `Demo@1234` |
| Name | Aarav Mehta |
| History | 8 months to the current month |
| Budgets | 7 categories per month |

The seed includes salary income, occasional freelance/dividend income, realistic
merchants, and occasional budget overruns so the insights and reports have
meaningful signals. All data is synthetic and generated with fixed seeds.

---

## Machine learning

### Expense category classifier

- **Input:** transaction description + amount bucket (`feature_utils.py`).
- **Preprocessing:** TF-IDF (`ngram_range=(1, 2)`, sublinear TF) inside a scikit-learn pipeline.
- **Candidates:** Logistic Regression, Multinomial Naive Bayes, Random Forest.
- **Split:** stratified 80/20, `random_state=42`.
- **Selection:** best weighted F1 (accuracy tie-breaker).
- **Persisted bundle:** pipeline, labels, metrics and metadata in
  `backend/ml/expense_classifier.pkl`.

Recorded evaluation (`backend/ml/classifier_metrics.json`):

| Model | Accuracy | Weighted precision | Weighted recall | Weighted F1 |
| --- | --- | --- | --- | --- |
| **Logistic Regression (selected)** | **1.0000** | **1.0000** | **1.0000** | **1.0000** |
| Multinomial Naive Bayes | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| Random Forest | 0.9844 | 0.9847 | 0.9844 | 0.9844 |

Dataset: 1,600 rows; 1,280 train / 320 test.

> **Why is accuracy perfect?** The synthetic dataset deliberately pairs distinct
> merchant phrases with categories (for example "Swiggy dinner order" → Food). On
> clean synthetic text this is an easy problem for linear models. The confusion
> matrix, classification report and per-class coefficients are still produced and
> included for evaluation. The API also stores every prediction and any human
> correction, so the model can be retrained on real correction data later.

### Expense forecasting

- **Targets:** total expenses plus all 8 expense categories.
- **Features:** linear time index, year, month, sine/cosine month encoding, quarter.
- **Candidates:** Linear Regression and Random Forest Regressor.
- **Validation:** chronological hold-out of the last 12 months (48 train / 12 test).
- **Metrics:** MAE, RMSE, R² per target; the best estimator per target is persisted.

Recorded total-expense result (`backend/ml/forecasting_metrics.json`):

| Metric | Linear Regression (selected) |
| --- | --- |
| MAE | ₹1,443.01 |
| RMSE | ₹1,795.06 |
| R² | 0.7529 |

Every category also selected Linear Regression on this dataset. The saved bundle
records the next forecast month and all comparison metrics.

**User-specific forecasts** are not a raw global-model dump. `forecast_service.py`
blends:

- the user's recent 3-month weighted average,
- a personal linear trend when at least 6 months of data exist,
- the trained seasonal category ratios.

If the user has fewer than three months of expenses, or no expenses in the current
month, the API returns an explicit `insufficient_data` message instead of inventing
a number. The UI labels every projection as an estimate.

Retrain both models:

```bash
python backend/ml/train_classifier.py
python backend/ml/train_forecasting.py
```

The backend loads the new Joblib bundles on restart (or after `reload_model()` in
`classifier_service.py`).

---

## REST API reference

All responses use:

```json
{ "success": true, "message": "...", "data": { } }
```

All endpoints except health/register/login require `Authorization: Bearer <token>`.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/health` | Health, database and model availability |
| `POST` | `/api/register` | Create account, returns JWT |
| `POST` | `/api/login` | Authenticate, returns JWT |
| `POST` | `/api/logout` | Revoke the current token |
| `GET` | `/api/me` | Current user |
| `GET` | `/api/transactions` | Paginated list with search/type/category/date filters |
| `POST` | `/api/transactions` | Create transaction; predicts category when omitted |
| `GET` | `/api/transactions/meta` | Total count and first/last transaction dates |
| `PUT` | `/api/transactions/<id>` | Update transaction; records corrections |
| `DELETE` | `/api/transactions/<id>` | Delete transaction |
| `GET` | `/api/dashboard?range=this_month` | Dashboard payload (`this_week`, `this_month`, `last_month`, `last_3_months`, `this_year`, `custom` + `date_from`/`date_to`) |
| `GET` | `/api/budgets?month=YYYY-MM` | Budgets, actual spend, summary, unbudgeted categories |
| `POST` | `/api/budgets` | Create budget |
| `PUT` | `/api/budgets/<id>` | Update budget |
| `DELETE` | `/api/budgets/<id>` | Delete budget |
| `POST` | `/api/predict-category` | Predict an expense category from description/amount |
| `POST` | `/api/predict-expenses` | User-specific next-month forecast |
| `GET` | `/api/ml/models` | Classifier and forecaster metadata/metrics |
| `GET` | `/api/insights?month=YYYY-MM` | Rule-based insights for a month |
| `POST` | `/api/chatbot` | Ask a question; `{ "message": "..." }` |
| `GET` | `/api/reports?month=YYYY-MM` | Full monthly report JSON |
| `GET` | `/api/reports/export?format=csv\|pdf&month=YYYY-MM` | Download report |

Example:

```bash
curl -X POST http://localhost:5000/api/login \
  -H "Content-Type: application/json" \
  -d '{"email":"demo@finora.local","password":"Demo@1234"}'

curl http://localhost:5000/api/dashboard?range=this_month \
  -H "Authorization: Bearer <TOKEN>"
```

---

## Datasets and retraining

All datasets live in `datasets/` and are generated deterministically with seed 42:

```bash
python datasets/generate_datasets.py
```

| File | Rows | Contents |
| --- | --- | --- |
| `expense_transactions.csv` | 1,612 raw (1,600 unique) | 24 months of labelled expense transactions, intentional blanks/duplicates for cleaning demonstration |
| `monthly_expenses.csv` | 60 | Monthly totals and 8 category columns with trend, seasonality and noise |
| `budget_data.csv` | 480 | Five simulated users × 12 months × 8 categories |
| `financial_insights.csv` | 22 | Insight rule templates |

Re-running the generator changes nothing because every random source is seeded.
Retrain after changing the datasets:

```bash
python backend/ml/train_classifier.py
python backend/ml/train_forecasting.py
```

---

## Jupyter notebooks

The `notebooks/` folder contains three executable walkthroughs:

1. **`01_dataset_exploration.ipynb`** — dataset shape, class balance, monthly trends,
   budget/insight files.
2. **`02_expense_classifier.ipynb`** — loads and cleans the data, trains all three
   candidates, displays the comparison table, classification report, confusion
   matrix, top TF-IDF coefficients and sample live predictions.
3. **`03_expense_forecasting.ipynb`** — plots history, trains both regressors,
   compares MAE/RMSE/R², displays the validation chart and inspects the saved bundle.

Launch:

```bash
jupyter lab
# then open the notebooks/ folder
```

Run the notebooks from the `notebooks/` directory. They resolve the project root
automatically relative to the current working directory.

---

## Testing

### Backend smoke suite

```bash
python backend/test_api.py
```

The suite creates a temporary SQLite database, then validates:

- health and anonymous-access rejection,
- registration, duplicate email, bad password, login, logout and revoked token,
- ML category prediction, transaction CRUD, prediction correction storage,
- budget CRUD and transaction-derived actual spend,
- dashboard dynamism, monthly series, insights, forecast, chatbot,
- reports JSON, CSV export, PDF export and ML metadata.

Expected final line:

```
All API smoke tests passed
```

### Frontend production build

```bash
cd frontend
npm run build
```

This is also a useful compile-time check for every page, import and Tailwind class.

### Manual acceptance checklist

- Register a fresh account → dashboard shows an empty state, no fake numbers.
- Add an expense without choosing a category → the AI suggestion appears and is saved.
- Correct the suggested category → edit the transaction; the prediction is marked corrected.
- Create budgets → utilisation matches the transactions in that month.
- Open Insights → only statements supported by your data appear.
- Ask the assistant "How much did I spend this month?" → answer matches the dashboard.
- Open Reports → change month, download CSV and PDF.
- Toggle dark mode, resize to mobile, open/close the sidebar.

---

## Production build

```bash
cd frontend
npm run build
cd ..
python backend/app.py
```

When `frontend/dist/` exists, Flask serves the built SPA at
<http://localhost:5000> (including client-side route fallback). Use a production
WSGI server such as Waitress or Gunicorn behind a reverse proxy for a real
deployment, and set strong `SECRET_KEY` / `JWT_SECRET` values.

Windows example:

```bash
pip install waitress
waitress-serve --listen=0.0.0.0:5000 backend.app:app
```

---

## Security and data isolation

- Every SQL query includes `user_id = %s` for the authenticated user.
- Ownership is re-checked on update/delete; another user's IDs return 404.
- JWT tokens are signed with `JWT_SECRET`, expire after `JWT_EXPIRES_HOURS`, and
  can be revoked through an in-memory denylist on logout.
- Passwords use Werkzeug's salted hash (`generate_password_hash`), never plaintext.
- Parameterised SQL is used throughout; no string interpolation of user values.
- CORS is restricted to the configured frontend origins.
- The frontend stores the token in `localStorage` for this educational app; for a
  higher-security deployment, prefer httpOnly cookies with CSRF protection.
- The assistant refuses investment, stock, tax and insurance advice and appends a
  disclaimer; it never queries outside data.

---

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `Can't connect to MySQL server` | Ensure MySQL is running, check `DB_HOST`/`DB_PORT`, and create the database with `python backend/init_db.py` |
| `Access denied for user` | Correct `DB_USER` / `DB_PASSWORD` in `.env` |
| `Expense forecasting model is not trained` | Run `python backend/ml/train_forecasting.py` |
| `Expense classifier is not trained` | Run `python backend/ml/train_classifier.py` |
| Frontend shows "Cannot reach the server" | Start Flask on port 5000 and confirm `http://localhost:5000/api/health` |
| CORS error in the browser | Add your frontend origin to `CORS_ORIGINS` in `.env` and restart Flask |
| Demo login fails | Run `python backend/seed_demo.py` against the same database |
| PDF download fails | `pip install -r requirements.txt` (ReportLab is required) |
| Port 5000 already in use | Stop the other process or change the port in `backend/app.py` and Vite's proxy target |
| `npm run build` cannot find modules | Run `npm install` inside `frontend/` |

For the SQLite fallback, remember that the environment variables must be set in the
same terminal that starts Flask. The `seed_demo.py` script must also use the same
`SQLITE_PATH`.

---

## Limitations and academic notes

- **Synthetic data:** all training data is generated locally; no real bank or personal
  data is used. Results are reproducible but easier than real-world transaction text,
  which is why classifier scores are very high.
- **Estimates, not advice:** forecasts are statistical projections. The app does not
  provide investment, tax, insurance or professional financial advice.
- **Small-data forecasting:** monthly category series are short; the personal forecast
  therefore blends a trained seasonal model with the user's recent weighted average
  and clearly signals when there is insufficient history.
- **Educational auth storage:** JWTs live in `localStorage` for simplicity. A production
  system should use httpOnly, secure cookies and a persistent token denylist.
- **Single-currency UI:** the interface formats amounts in INR (`₹`), while the database
  stores plain decimals.
- **No bank integrations:** transactions are entered manually or seeded; there is no
  external aggregator or scraping.

---

### Suggested project-report talking points

1. Problem statement and motivation for personal-finance analytics.
2. System architecture (React SPA ↔ Flask API ↔ MySQL, ML bundles).
3. Dataset generation methodology and ethical use of synthetic data.
4. Classifier pipeline, model comparison and confusion matrix.
5. Forecasting design, chronological validation and user-level blending.
6. Rule-based insight engine and grounded chatbot design.
7. Security: JWT, route guard, user-scoped queries, validation.
8. Testing strategy and results.
9. Limitations and future work (real correction-based retraining, recurring
   transactions, multi-currency, httpOnly cookies, deployment).

---

**Finora** — an educational final-year project. Built with React, Flask, MySQL and
scikit-learn.
