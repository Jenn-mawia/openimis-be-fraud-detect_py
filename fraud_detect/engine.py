"""
ML scoring engine for the fraud detection module.

Wraps the trained Isolation Forest model and scaler (from Phase 3) and exposes
a single scoring function.  Model artefacts are loaded lazily on first use so
that importing this module at startup does not raise errors when the .joblib
files are absent (e.g. in unit-test environments that mock the loader).

Placeholder behaviour:
  - If the model files are missing (because Phase 3 has not yet been run), the
    engine returns a neutral score (0.0, is_anomaly=False) with a warning logged
    rather than crashing.  This lets the rules engine continue to work end-to-end
    even before the ML artefacts are available.
"""

import logging
import os

import numpy as np

logger = logging.getLogger(__name__)

_MODEL = None
_SCALER = None

# Feature order MUST match the order used during training (Phase 2 / Phase 3).
FEATURE_ORDER = [
    "invoice_inflation_ratio",
    "claim_lag_days",
    "icd_is_vague",
    "provider_avg_inflation",
    "provider_claim_count",
    "member_claim_count",
    "amount_vs_benchmark",
    "had_pre_audit_adjustment",
]

# ICD codes considered vague — kept in sync with rules.py
VAGUE_ICD_CODES = frozenset([
    "Z51.9", "Z00.0", "Z76.9", "Z71.9", "Z53.9",
])

_MODELS_DIR = os.path.join(os.path.dirname(__file__), "..", "models")
_MODEL_PATH = os.path.join(_MODELS_DIR, "fraud_model.joblib")
_SCALER_PATH = os.path.join(_MODELS_DIR, "fraud_scaler.joblib")

_NEUTRAL_RESULT = {"anomaly_score": 0.0, "is_anomaly": False}


def _load_models():
    """
    Lazily loads the trained Isolation Forest model and StandardScaler.
    Returns True if the models were loaded successfully, False otherwise.
    """
    global _MODEL, _SCALER
    if _MODEL is not None:
        return True

    # Allow test/CI environments to override artefact paths via env vars.
    model_path = os.environ.get("FRAUD_MODEL_PATH", _MODEL_PATH)
    scaler_path = os.environ.get("FRAUD_SCALER_PATH", _SCALER_PATH)

    if not os.path.exists(model_path) or not os.path.exists(scaler_path):
        logger.warning(
            "Fraud detection model artefacts not found at %s / %s. "
            "ML scoring will return neutral results until artefacts are provided. "
            "Run the Phase 3 training script to generate them.",
            model_path,
            scaler_path,
        )
        return False

    try:
        import joblib  # noqa: PLC0415 — deferred import to keep startup lean
        _MODEL = joblib.load(model_path)
        _SCALER = joblib.load(scaler_path)
        logger.info("Fraud detection model loaded from %s", model_path)
        return True
    except Exception as exc:
        logger.exception("Failed to load fraud detection model: %s", exc)
        return False


def _extract_features(claim_dict):
    """
    Converts a claim dict into the 8-element numpy feature vector expected by
    the trained model.  Uses the same transformations applied in Phase 2.
    """
    claimed = float(claim_dict.get("claimed_amount") or 0)
    settled = float(claim_dict.get("approved_amount") or claimed or 1)
    inflation_ratio = min(claimed / settled if settled > 0 else 1.0, 10.0)

    service_date = claim_dict.get("date_from")
    claim_date = claim_dict.get("date_claimed")
    if service_date and claim_date:
        # Dates may arrive as strings (e.g. "2025-09-01") from a JSON POST body
        # or as datetime.date objects from the ORM signal handler.
        if isinstance(service_date, str):
            from datetime import date as _date  # noqa: PLC0415
            service_date = _date.fromisoformat(service_date)
        if isinstance(claim_date, str):
            from datetime import date as _date  # noqa: PLC0415
            claim_date = _date.fromisoformat(claim_date)
        lag_days = max((claim_date - service_date).days, 0)
    else:
        lag_days = 0

    icd_is_vague = 1 if claim_dict.get("icd_code") in VAGUE_ICD_CODES else 0

    # Provider- and member-level aggregate features.
    # In production these are pre-computed and injected into the claim dict.
    # Fall back to neutral values (1.0 / 1) when not available so the function
    # degrades gracefully on any individual claim call.
    provider_avg_inflation = float(claim_dict.get("provider_avg_inflation") or 1.0)
    provider_claim_count = int(claim_dict.get("provider_claim_count") or 1)
    member_claim_count = int(claim_dict.get("member_claim_count") or 1)
    amount_vs_benchmark = float(claim_dict.get("amount_vs_benchmark") or 1.0)

    # An adjustment was made before audit whenever the settled amount was reduced
    # below the invoiced amount (inflation_ratio > 1.0).  The fact that any
    # adjustment was needed is itself a weak fraud signal — the original
    # submission was not right.
    had_pre_audit_adjustment = 1 if inflation_ratio > 1.0 else 0

    return np.array([[
        inflation_ratio,
        lag_days,
        icd_is_vague,
        provider_avg_inflation,
        provider_claim_count,
        member_claim_count,
        amount_vs_benchmark,
        had_pre_audit_adjustment,
    ]], dtype=float)


def _features_as_dataframe(claim_dict):
    """
    Returns a single-row DataFrame with the feature columns named to match
    those used during scaler training, suppressing sklearn's feature-name warning.
    """
    import pandas as pd  # noqa: PLC0415
    row = _extract_features(claim_dict)
    return pd.DataFrame(row, columns=FEATURE_ORDER)


def score_claim_ml(claim_dict):
    """
    Scores a single claim for anomaly using the trained Isolation Forest.

    Args:
        claim_dict: dict with claim fields (see module docstring for expected keys).

    Returns:
        dict with:
          - anomaly_score (float): decision_function output. More negative = more anomalous.
          - is_anomaly (bool): True when the model predicts this claim is an outlier.
    """
    if not _load_models():
        return _NEUTRAL_RESULT

    try:
        features = _features_as_dataframe(claim_dict)
        features_scaled = _SCALER.transform(features)
        score = float(_MODEL.decision_function(features_scaled)[0])
        prediction = _MODEL.predict(features_scaled)[0]  # -1 = anomaly, 1 = normal
        return {
            "anomaly_score": score,
            "is_anomaly": prediction == -1,
        }
    except Exception as exc:
        logger.exception("ML scoring failed for claim_dict: %s", exc)
        return _NEUTRAL_RESULT


def compute_risk_level(rules_result, ml_result):
    """
    Combines the rules engine output and ML output into a single risk level string.

    Decision matrix:
      rules_flagged=True  AND  ml_anomaly=True   -> HIGH  (dual confirmation)
      2+ rules fired (regardless of ML)          -> HIGH  (high-confidence rules)
      rules_flagged=True  XOR  ml_anomaly=True   -> MEDIUM
      Neither flagged but anomaly_score < -0.1   -> MEDIUM  (ML near-miss)
      All clear                                  -> LOW

    The "2+ rules" threshold handles the pre-ML phase: when model artefacts
    are not yet available ml_anomaly is always False, but a claim that trips
    two or more independent rules simultaneously still warrants HIGH.

    Args:
        rules_result: dict from evaluate_rules() — must have 'is_flagged' and
                      'fired_rules' (list of rule dicts).
        ml_result:    dict from score_claim_ml() — must have 'is_anomaly' and
                      'anomaly_score'.

    Returns:
        str: "HIGH", "MEDIUM", or "LOW"
    """
    rule_flagged = rules_result.get("is_flagged", False)
    fired_count = len(rules_result.get("fired_rules", []))
    ml_anomaly = ml_result.get("is_anomaly", False)
    ml_score = ml_result.get("anomaly_score", 0.0)

    if (rule_flagged and ml_anomaly) or fired_count >= 2:
        return "HIGH"
    if rule_flagged or ml_anomaly:
        return "MEDIUM"
    if ml_score < -0.1:
        return "MEDIUM"
    return "LOW"
