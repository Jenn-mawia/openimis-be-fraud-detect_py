# Claims Fraud Triage — demo UI

A Streamlit front end for the openIMIS `fraud_detect` module. Every screen maps
directly onto the module's REST API — nothing in the UI is mocked.

## Run it

With the openIMIS Docker stack running:

```bash
cd fraud-demo-ui
pip install -r requirements.txt
streamlit run app.py
```

Then open http://localhost:8501. The sidebar's API base URL defaults to
`http://localhost/api/fraud_detect` (the module's mount point behind the
openIMIS gateway). Use **Test connection** in the sidebar to verify.

If your API requires authentication, paste a bearer token in the sidebar —
otherwise leave it empty.

## The three screens

1. **Triage dashboard** — `GET /flags/`. Live claim log with risk-level
   filtering, headline counts, and score distributions. If it's empty, seed
   demo claims in the backend first:
   `docker compose exec backend sh -c "cd /openimis-be/openIMIS && python manage.py seed_demo_claims"`
2. **Score a claim** — `POST /score/`. Assesses a claim on demand (no database
   write) through the 5 business rules and the Isolation Forest model, and
   explains the resulting category using the module's actual decision matrix.
   The three preset buttons prefill claims that demonstrate a clean claim, an
   inflated invoice, and a late submission with a vague ICD code.
3. **Review & override** — `GET /flags/{id}`, `POST /rescore/{id}`,
   `POST /override/`. Look up a scored claim, re-score it against the live
   database record, and record an APPROVE / REJECT / ESCALATE decision, which
   is persisted for the retraining pipeline.

## Suggested 3-minute demo script

1. Dashboard: "every claim in the system has already been scored — here's the
   risk breakdown." Filter to HIGH.
2. Score a claim: click **Clean claim** → LOW. Click **Inflated invoice** →
   watch the rule card and ML verdict appear. Nudge the invoiced amount down
   and re-assess to show the threshold behavior live.
3. Review & override: pull up one of the HIGH claims from the dashboard,
   disagree with it (APPROVE + a note), and show the saved confirmation —
   the human-in-the-loop story.
