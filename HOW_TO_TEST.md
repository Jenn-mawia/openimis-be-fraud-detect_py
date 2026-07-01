# How to Test the Fraud Detection Module

This guide walks through every step needed to verify the module is correctly
installed, migrated, and running inside the openIMIS Docker stack.
All commands are run from the `openimis-dist_dkr/` directory unless stated
otherwise.

---

## Prerequisites

- The openIMIS Docker stack is running (`docker compose ps` shows all services
  `Up`).
- The module source is at `../openimis-be-fraud-detect_py` relative to
  `openimis-dist_dkr/`.
- `compose.fraud-detect.yml` exists in `openimis-dist_dkr/` (created as part
  of the module setup).

---

## Step 1 — Register the module with the backend

The backend reads `openimis.json` at startup to know which Django apps to load.
The fraud detection module must be listed there.

Open `openimis-be_py/openimis.json` and confirm (or add) this entry at the end
of the `"modules"` array:

```json
{
  "name": "fraud_detect",
  "pip": "openimis-be-fraud-detect",
  "url": "fraud_detect.urls"
}
```

`"url": "fraud_detect.urls"` tells the openIMIS URL router to include the
module's REST endpoints under `/api/`.

---

## Step 2 — Restart the backend with the fraud-detect overlay

The base Docker image does not include our module. The overlay file
`compose.fraud-detect.yml` mounts the local source directory into the container
and installs it with `pip install -e` every time the container starts.

```bash
# Restart only the backend and worker services using both compose files.
# --no-deps prevents Docker from also recreating unrelated services.
docker compose -f compose.yml -f compose.fraud-detect.yml up -d --no-deps backend worker
```

> **What this does**: Docker mounts `../openimis-be-fraud-detect_py` as
> `/openimis-be-fraud-detect` inside the container, overrides the entrypoint to
> `pip install -e /openimis-be-fraud-detect` before starting Django, and mounts
> the updated `openimis.json` so the app is registered.

> **Startup time**: On a **fresh container** (e.g. after `--force-recreate`),
> the entrypoint installs `scikit-learn`, `joblib`, `pandas`, and `numpy` from
> scratch — this takes 2–3 minutes the first time. On a **container restart**
> (same container, already has ML deps), the entrypoint detects the packages are
> present and skips the heavy install, cutting startup to roughly 5–10 seconds.

---

## Step 3 — Run the database migration

This creates the three new tables the module needs:
- `tbl_FraudFlag` — one row per scored claim
- `tbl_ReviewerOverride` — reviewer decisions
- `tbl_FraudModelVersion` — tracks which ML model artefact is active

```bash
# pip install inside the container first (idempotent), then run the migration.
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  sh -c "pip install -e /openimis-be-fraud-detect -q && \
         python manage.py migrate fraud_detect"
```

Expected output (last two lines):
```
Running migrations:
  Applying fraud_detect.0001_initial... OK
```

### Verify the tables were created

`\dt *Fraud*` uses a case-sensitive glob in psql and will NOT match mixed-case
table names. Use `information_schema` instead:

```bash
docker compose exec db psql -U IMISuser -d IMIS -c "
  SELECT table_name
  FROM information_schema.tables
  WHERE table_name ILIKE '%fraud%'
     OR table_name ILIKE '%reviewer%'
     OR table_name ILIKE '%modelversion%';"
```

Expected output:
```
     table_name
---------------------
 tbl_FraudFlag
 tbl_ReviewerOverride
 tbl_FraudModelVersion
```

You can also describe a specific table directly:

```bash
docker compose exec db psql -U IMISuser -d IMIS -c '\d "tbl_FraudFlag"'
```

---

## Step 4 — Set up the test database (one-time setup)

Django's test runner creates a fresh `test_imis` database by running all
migrations from scratch. This fails in openIMIS because some legacy migrations
contain deferred SQL that references `tblUsers` before it is created — a
known openIMIS issue unrelated to this module.

The fix is to clone the already-populated `IMIS` database as the test database
once, then reuse it with `--keepdb` on every subsequent run.

### 4a — Terminate active connections to IMIS

`CREATE DATABASE ... TEMPLATE` requires no other sessions to be connected to
the source database. We connect to the idle `postgres` database to run the
termination command (so we ourselves are not connected to `IMIS`):

```bash
# Connect to the 'postgres' database (not the 'postgres' role — IMISuser owns it).
# This terminates every backend connection to IMIS except our own session.
docker compose exec db psql -U IMISuser -d postgres -c "
  SELECT pg_terminate_backend(pid)
  FROM pg_stat_activity
  WHERE datname = 'IMIS' AND pid <> pg_backend_pid();"
```

> The backend container will automatically reconnect to `IMIS` within seconds —
> this termination is safe and causes no data loss.

### 4b — Drop any stale test database

```bash
# Remove test_imis if it exists from a previous failed run.
docker compose exec db psql -U IMISuser -d postgres \
  -c "DROP DATABASE IF EXISTS test_imis;"
```

### 4c — Clone IMIS as the test database

```bash
# "IMIS" must be quoted because PostgreSQL folds unquoted identifiers to
# lowercase, and the database name is uppercase.
docker compose exec db psql -U IMISuser -d postgres \
  -c 'CREATE DATABASE test_imis TEMPLATE "IMIS";'
```

Expected output:
```
CREATE DATABASE
```

> This copies the full schema AND data from `IMIS` into `test_imis`, including
> the already-applied `fraud_detect` migration, so Django's `--keepdb` flag
> finds everything it needs.

---

## Step 5 — Run the unit tests

```bash
# --keepdb   : reuse the existing test_imis database instead of recreating it.
#              Without this flag Django would try to build test_imis from scratch
#              and hit the tblUsers error described in Step 4.
# --verbosity=2 : print each test name as it runs so you can see what passed.
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  sh -c "pip install -e /openimis-be-fraud-detect -q && \
         python manage.py test fraud_detect --keepdb --verbosity=2"
```

### Expected output

```
Found 36 test(s).
Using existing test database for alias 'default' ('test_imis')...
...
Ran 36 tests in 0.15s

OK
Preserving test database for alias 'default' ('test_imis')...
```

All 36 tests should show `ok`. Two expected warnings appear in the output:

1. **`test_returns_neutral_result_on_model_exception`** prints a traceback —
   this is **intentional**. The logger prints the caught exception to confirm the
   error-handling path works. The test is still marked `ok`.

2. **`Your models in app(s): 'claim', 'contribution', 'core', 'payroll' have
   changes that are not yet reflected in a migration`** — this is a known
   upstream openIMIS issue unrelated to `fraud_detect`. Django prints the
   warning but all tests continue to pass.

### Test coverage summary

| Test class | Count | What it verifies |
|---|---|---|
| `MLScoringTestCase` | 7 | `score_claim_ml()` returns correct types, handles missing model files and exceptions without crashing |
| `RiskLevelTestCase` | 9 | `compute_risk_level()` returns HIGH / MEDIUM / LOW correctly for all combinations, including the 2+ rules → HIGH path |
| `RulesEngineTestCase` | 20 | All 5 rules fire at the right thresholds, boundary conditions, missing data gracefully handled |

---

## Step 6 — Train the ML model

The Isolation Forest model is **not trained automatically**. Without the
`.joblib` artefacts the ML layer returns a neutral score (`0.0`) while the
rules engine still works. Run the training command once after placing the
feature dataset in `data/claims_features.csv`.

### 6a — Verify the feature CSV is in place

The CSV must contain these seven columns (extra columns like `proxy_fraud_label`
are ignored):

```
invoice_inflation_ratio, claim_lag_days, icd_is_vague,
provider_avg_inflation, provider_claim_count, member_claim_count,
amount_vs_benchmark
```

```bash
head -2 ../openimis-be-fraud-detect_py/data/claims_features.csv
```

### 6b — Run the training command

```bash
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  python manage.py retrain_fraud_model
```

Expected output:

```
Loading base feature data from /openimis-be-fraud-detect/data/claims_features.csv …
Reviewer overrides available for feedback: 0 (false-positive corrections)
Training on 422382 rows, contamination=0.08, n_estimators=200 …
Model training complete.
Model saved to /openimis-be-fraud-detect/models/fraud_model.joblib
Scaler saved to /openimis-be-fraud-detect/models/fraud_scaler.joblib
Model version 1 recorded and set as active.
```

The two `.joblib` files are saved to `../openimis-be-fraud-detect_py/models/`
on the host (via the bind mount), so they survive container restarts.

> **After training, restart the backend** so the new artefacts are loaded into
> the gunicorn workers:
> ```bash
> docker compose -f compose.yml -f compose.fraud-detect.yml restart backend
> # Wait ~30–60 s, then poll:
> until curl -sf http://localhost/api/fraud_detect/flags/ | grep -q count; do sleep 3; done
> echo "Backend ready"
> ```

---

## Step 7 — Verify the live REST API

The backend must be running with the fraud-detect overlay (Step 2). The API
is exposed through the nginx proxy on port 80.

> **URL structure**: openIMIS automatically mounts every module at
> `/api/<module_name>/` (from `openimisurls.py`). Our module name is
> `fraud_detect`, so all endpoints live under `/api/fraud_detect/`.

> **Shell tip**: Always write `curl` commands as a **single line** or use
> `$'...'` quoting. A bare backslash-newline continuation can silently split
> the command and cause `zsh: command not found: -H` errors.

### On-demand score (no DB required)

This endpoint scores a raw claim dict without saving anything — useful for
quick smoke-testing.

**With trained ML model** (`date_from` / `date_claimed` accepted as ISO strings):

```bash
curl -s -X POST http://localhost/api/fraud_detect/score/ -H "Content-Type: application/json" -d '{"claimed_amount": 25000, "approved_amount": 3000, "icd_code": "Z51.9", "date_from": "2025-01-01", "date_claimed": "2025-04-15"}' | python3 -m json.tool
```

Expected response:

```json
{
  "rules": {
    "is_flagged": true,
    "fired_rules": [
      {"name": "Invoice inflation above 3x", "description": "..."},
      {"name": "Vague ICD code used", "description": "..."},
      {"name": "High-value claim with vague diagnosis", "description": "..."}
    ]
  },
  "ml": {
    "anomaly_score": -0.11,
    "is_anomaly": true
  },
  "overall_risk_level": "HIGH"
}
```

> **If `anomaly_score` is `0.0`**: the ML model artefacts are not loaded yet.
> Complete Step 6 first, then restart the backend.

### Test a maximally fraudulent claim

This claim triggers all 4 rules **and** the ML anomaly detector simultaneously:

```bash
curl -s -X POST http://localhost/api/fraud_detect/score/ -H "Content-Type: application/json" -d '{"claimed_amount": 50000, "approved_amount": 1500, "icd_code": "Z51.9", "date_from": "2025-09-01", "date_claimed": "2026-07-01", "provider_avg_inflation": 3.5, "provider_claim_count": 80, "member_claim_count": 1, "amount_vs_benchmark": 8.0}' | python3 -m json.tool
```

Expected:
- `overall_risk_level`: `"HIGH"`
- `ml.is_anomaly`: `true`, `ml.anomaly_score` ≈ `−0.305`
- `rules.fired_rules`: 3 rules (inflation 33×, vague ICD, high-value+vague)

### List all fraud flags

```bash
# Returns an empty results array until claims are seeded (Step 8).
curl -s http://localhost/api/fraud_detect/flags/ | python3 -m json.tool
```

### Filter by risk level

```bash
curl -s "http://localhost/api/fraud_detect/flags/?risk_level=HIGH" | python3 -m json.tool
```

---

## Step 8 (Optional) — Seed demo claims and verify auto-flagging

The `seed_demo_claims` management command creates four synthetic claims
designed to demonstrate all risk levels:

| Claim | Scenario | Expected risk |
|---|---|---|
| DEMO-A | Clean lab test, 3,000 KES, filed same day | LOW |
| DEMO-B | 120-day lag + 4.5× invoice inflation | HIGH |
| DEMO-C | Invoice 25,000 KES, settled 3,000 KES (inflation 8×) | HIGH (with ML) / MEDIUM (without) |
| DEMO-D | Normal claim, 4,500 KES | LOW |

> **ICD code note**: The seed command tries to look up ICD codes Z51.9, J06.9,
> and H52.1 in the database. If those codes are not present (common in fresh
> installs), all four claims fall back to the first available diagnosis. This
> means the vague-ICD and high-value+vague rules will not fire, but DEMO-B
> still reaches HIGH via 2 rules (lag + inflation) and DEMO-C via ML anomaly
> detection.

```bash
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  python manage.py seed_demo_claims
```

Then confirm the claims were scored automatically by the `post_save` signal:

```bash
# Fetch all HIGH-risk flags — should contain DEMO-B and DEMO-C
curl -s "http://localhost/api/fraud_detect/flags/?risk_level=HIGH" | python3 -m json.tool

# Fetch all LOW-risk flags — should contain DEMO-A and DEMO-D
curl -s "http://localhost/api/fraud_detect/flags/?risk_level=LOW" | python3 -m json.tool
```

### Re-scoring existing claims after model update

If you retrain the model (Step 6) after claims have already been scored, the
existing `tbl_FraudFlag` rows still hold the old scores. Re-score manually
from the Django shell:

```bash
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend python manage.py shell
```

```python
from claim.models import Claim
from fraud_detect.models import FraudFlag
from fraud_detect.engine import compute_risk_level, score_claim_ml
from fraud_detect.rules import evaluate_rules

for c in Claim.objects.filter(code__startswith="DEMO").order_by("code"):
    d = {
        "claimed_amount": float(c.claimed or 0),
        "approved_amount": float(c.approved or 0),
        "date_from": c.date_from,
        "date_claimed": c.date_claimed,
        "icd_code": c.icd.code if c.icd else None,
    }
    rules = evaluate_rules(d)
    ml = score_claim_ml(d)
    risk = compute_risk_level(rules, ml)
    FraudFlag.objects.update_or_create(
        claim_id=c.id,
        defaults={
            "is_rule_flagged": rules["is_flagged"],
            "rule_flag_reasons": rules["fired_rules"],
            "anomaly_score": ml["anomaly_score"],
            "is_ml_anomaly": ml["is_anomaly"],
            "overall_risk_level": risk,
        },
    )
    print(f"{c.code}: {len(rules['fired_rules'])} rules -> {risk}")
```

---

## Quick reference — commands to run every time

After the one-time setup in Steps 1–6 is complete, the daily workflow is:

```bash
# From openimis-dist_dkr/

# Start the stack with the fraud-detect overlay
# First start after --force-recreate takes ~2-3 min (ML deps install);
# subsequent restarts of the same container take ~5-10 sec.
docker compose -f compose.yml -f compose.fraud-detect.yml up -d --no-deps backend worker

# Run tests
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  python manage.py test fraud_detect --keepdb

# Smoke-test the API (rules + ML scoring, single-line curl)
curl -s -X POST http://localhost/api/fraud_detect/score/ -H "Content-Type: application/json" -d '{"claimed_amount": 50000, "approved_amount": 1500, "icd_code": "Z51.9", "date_from": "2025-09-01", "date_claimed": "2026-07-01", "provider_avg_inflation": 3.5, "provider_claim_count": 80, "amount_vs_benchmark": 8.0}' | python3 -m json.tool

# Retrain the ML model (run after updating claims_features.csv)
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  python manage.py retrain_fraud_model
```

### Decision logic reference

| Condition | Risk level |
|---|---|
| 2+ rules fired (regardless of ML) | HIGH |
| Rules flagged AND ML anomaly | HIGH |
| Rules flagged XOR ML anomaly | MEDIUM |
| ML anomaly score < −0.1 (near-miss) | MEDIUM |
| Nothing flagged | LOW |
