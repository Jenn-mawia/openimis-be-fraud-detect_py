# Fraud Detection — Model Performance Report

This report describes the currently active Isolation Forest model artefacts in
this directory (`fraud_model.joblib` + `fraud_scaler.joblib`).

Regenerate it by re-running the evaluation after any `retrain_fraud_model` run.

---

## Model

| Property | Value |
|----------|-------|
| Algorithm | Isolation Forest (unsupervised) |
| Estimators | 200 |
| Contamination | 0.08 |
| Random state | 42 |
| Features | 8 |
| Training rows | 422,382 |
| Scaler | `StandardScaler` |

**Features** (order matters — must match `engine.FEATURE_ORDER`):
`invoice_inflation_ratio`, `claim_lag_days`, `icd_is_vague`,
`provider_avg_inflation`, `provider_claim_count`, `member_claim_count`,
`amount_vs_benchmark`, `had_pre_audit_adjustment`.

---

## Evaluation

Evaluated on a held-out test set of **84,477 claims** (20% split,
`random_state=42`). The proxy fraud label is `1` when
`SETTLED AMOUNT < 80% of INVOICE AMOUNT` — claims where the insurer already
detected something wrong and partially rejected the claim.

| Class | Precision | Recall | F1-score | Support |
|-------|-----------|--------|----------|---------|
| Normal | 0.9210 | 0.9461 | 0.9334 | 75,595 |
| Suspicious | 0.4032 | 0.3097 | 0.3503 | 8,882 |
| **Macro avg** | **0.6621** | **0.6279** | **0.6419** | **84,477** |
| **Weighted avg** | **0.8666** | **0.8792** | **0.8721** | **84,477** |

**Overall accuracy**: 87.9% &nbsp;|&nbsp; **ROC-AUC**: 0.847

**Confusion Matrix** (test set):

```
                     Predicted Normal   Predicted Suspicious
Actual Normal              71,523              4,072
Actual Suspicious           6,131              2,751
```

- True Negatives (correctly cleared): **71,523**
- False Positives (wrongly flagged): **4,072**
- False Negatives (missed suspicious): **6,131**
- True Positives (correctly caught): **2,751**

Of 8,882 actually-suspicious claims, the model flagged **6,823** claims as
anomalies overall.

---

## Interpretation

The model correctly clears 71,523 normal claims (94.6% specificity) and catches
2,751 suspicious claims it would otherwise miss. Adding the
`had_pre_audit_adjustment` feature raised ROC-AUC from **0.770** (7-feature
model) to **0.847** and improved the Suspicious-class F1 from 0.26 to 0.35.

The still-modest precision on the Suspicious class (0.40) reflects the
imprecision of the proxy label — not every claim settled below invoice was
fraudulent; some were legitimately partially approved. The ROC-AUC of 0.847
indicates strong discrimination power well above chance.

> The rules engine supplements the ML model. A claim that fires two or more
> rules reaches HIGH risk even when the ML score is near neutral, ensuring
> explainable high-confidence flagging works without model artefacts.

---

## Reproducing this report

```bash
docker compose -f compose.yml -f compose.fraud-detect.yml exec backend \
  python manage.py retrain_fraud_model   # (re)train from data/claims_features.csv
```

Then evaluate the saved artefacts against the same 80/20 split
(`random_state=42`) using the 8 feature columns above and the
`proxy_fraud_label` column, reporting `classification_report`,
`confusion_matrix`, and `roc_auc_score(y_test, -decision_function)`.
