Updated todo list


**✅ Complete**

| Phase | Status | Notes |
|---|---|---|
| 0 — Environment Setup | ✅ | Docker stack running, repos cloned |
| 1 — Data Exploration | ✅ | CSV exists at `data/claims_features.csv` |
| 2 — Feature Engineering | ✅ | All 7 features present in CSV |
| 3 — Model Training | ✅ | Isolation Forest trained on 422k rows; `.joblib` files saved |
| 4 — Django Module | ✅ | All 12 steps: models, rules, engine, signals, views, urls, schema, migrations |
| 5 — FHIR Extensions | ✅ | `fhir_extensions.py` created |
| 6 — Feedback Loop | ✅ | retrain_fraud_model.py management command |
| 7 — Unit Tests | ✅ | 36 tests passing |

---

**❌ Missing**

**Phase 8 — Frontend Integration** — Nothing done in openimis-fe_js. The plan requires a `FraudRiskBadge` React component added to the claims list. Also note: the URL in the plan (`/api/fraud/flags/${claimId}/`) is wrong — it must be `/api/fraud_detect/flags/${claimId}/`.

**Phase 9 — Performance Report** — The model was trained but the evaluation script (precision/recall/F1 table + confusion matrix heatmap) was never run against the held-out test set from Phase 3. This is a **required deliverable** for Track 3 judging.

**Phase 10 — Documentation:**
- Step 10.1 — Proper README with all 9 required sections (problem statement, architecture diagram, responsible AI section, performance numbers, etc.) — **not written**
- Step 10.2 — Model Card (`MODEL_CARD.md`) — **not written**
- Step 10.3 — compose.fraud-detect.yml — ✅ already done
- Step 10.4 — Draft PR on `openimis/openimis-be_py` — **not opened**

**Phase 11 — Demo Preparation:**
- Step 11.1 — `seed_demo_claims` command — ✅ already done and run
- Step 11.2 — 8-minute demo script — **not written**
- Step 11.3 — Final commit, `v1.0-hackathon` git tag, final PR — **not done**

---

**Priority order for remaining work:**

1. **Phase 9** (performance report) — generates the numbers needed for the README and model card
2. **Phase 10.1/10.2** (README + model card) — judges read this before the demo
3. **Phase 8** (frontend badge) — the demo requires clicking on a coloured badge in the claims list; without it the demo script doesn't work
4. **Phase 10.4 / 11.3** (draft PR + tag) — final submission requirement
5. **Phase 11.2** (demo script) — rehearsal prep