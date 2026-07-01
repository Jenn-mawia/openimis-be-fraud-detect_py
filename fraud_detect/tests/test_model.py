"""
Unit tests for the ML scoring engine.

The tests mock the model artefacts so they run without requiring the trained
.joblib files to be present (i.e. before Phase 3 is complete).

Run with:
    docker compose exec backend python manage.py test fraud_detect.tests.test_model
"""

from datetime import date
from unittest.mock import MagicMock, patch

from django.test import TestCase

from fraud_detect.engine import compute_risk_level, score_claim_ml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_model(decision_score=-0.5, predict_result=-1):
    """Returns a mock Isolation Forest that returns deterministic values."""
    model = MagicMock()
    model.decision_function.return_value = [decision_score]
    model.predict.return_value = [predict_result]
    return model


def _make_mock_scaler():
    """Returns a mock StandardScaler that passes data through unchanged."""
    scaler = MagicMock()
    scaler.transform.side_effect = lambda x: x
    return scaler


# ---------------------------------------------------------------------------
# Tests for score_claim_ml()
# ---------------------------------------------------------------------------

class MLScoringTestCase(TestCase):

    def _clean_claim(self):
        return {
            "claimed_amount": 5000,
            "approved_amount": 5000,
            "date_from": date(2025, 3, 1),
            "date_claimed": date(2025, 3, 3),
            "icd_code": "J06.9",
        }

    def _suspicious_claim(self):
        return {
            "claimed_amount": 20000,
            "approved_amount": 3000,
            "date_from": date(2025, 1, 1),
            "date_claimed": date(2025, 6, 1),
            "icd_code": "Z51.9",
        }

    @patch("fraud_detect.engine._load_models")
    def test_returns_neutral_result_when_model_unavailable(self, mock_load):
        """When model files are missing, a neutral result is returned (no crash)."""
        mock_load.return_value = False
        result = score_claim_ml(self._clean_claim())
        self.assertEqual(result["anomaly_score"], 0.0)
        self.assertFalse(result["is_anomaly"])

    def test_score_claim_returns_required_keys(self):
        """Result must always contain anomaly_score and is_anomaly."""
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model()),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertIn("anomaly_score", result)
        self.assertIn("is_anomaly", result)

    def test_anomaly_score_is_float(self):
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model(decision_score=-0.4)),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertIsInstance(result["anomaly_score"], float)

    def test_is_anomaly_is_bool(self):
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model()),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertIsInstance(result["is_anomaly"], bool)

    def test_anomaly_true_when_model_predicts_minus_one(self):
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model(predict_result=-1)),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertTrue(result["is_anomaly"])

    def test_anomaly_false_when_model_predicts_one(self):
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model(predict_result=1)),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertFalse(result["is_anomaly"])

    def test_returns_neutral_result_on_model_exception(self):
        """Exceptions inside the model call must not propagate."""
        broken_model = MagicMock()
        broken_model.decision_function.side_effect = RuntimeError("model broken")
        with (
            patch("fraud_detect.engine._MODEL", broken_model),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml(self._clean_claim())
        self.assertEqual(result["anomaly_score"], 0.0)
        self.assertFalse(result["is_anomaly"])

    def test_missing_claim_fields_do_not_crash(self):
        """An empty dict must not raise; engine falls back to neutral defaults."""
        with (
            patch("fraud_detect.engine._MODEL", _make_mock_model(predict_result=1)),
            patch("fraud_detect.engine._SCALER", _make_mock_scaler()),
        ):
            result = score_claim_ml({})
        self.assertIn("anomaly_score", result)


# ---------------------------------------------------------------------------
# Tests for compute_risk_level()
# ---------------------------------------------------------------------------

class RiskLevelTestCase(TestCase):

    def _rules(self, flagged, fired=None):
        return {"is_flagged": flagged, "fired_rules": fired or []}

    def _ml(self, is_anomaly, score=0.0):
        return {"is_anomaly": is_anomaly, "anomaly_score": score}

    def test_high_when_both_layers_flag(self):
        level = compute_risk_level(
            self._rules(True, [{"name": "test"}]),
            self._ml(True, -0.5),
        )
        self.assertEqual(level, "HIGH")

    def test_high_when_two_or_more_rules_fire_no_ml(self):
        """2+ simultaneous rules → HIGH even when the ML model is absent."""
        two_rules = [{"name": f"r{i}"} for i in range(2)]
        level = compute_risk_level(
            self._rules(True, two_rules),
            self._ml(False, 0.0),  # neutral ML (no artefacts loaded)
        )
        self.assertEqual(level, "HIGH")

    def test_high_when_five_rules_fire_no_ml(self):
        five_rules = [{"name": f"r{i}"} for i in range(5)]
        level = compute_risk_level(
            self._rules(True, five_rules),
            self._ml(False, 0.0),
        )
        self.assertEqual(level, "HIGH")

    def test_medium_when_only_rules_flag(self):
        level = compute_risk_level(
            self._rules(True, [{"name": "test"}]),
            self._ml(False, 0.3),
        )
        self.assertEqual(level, "MEDIUM")

    def test_medium_when_only_ml_flags(self):
        level = compute_risk_level(
            self._rules(False),
            self._ml(True, -0.5),
        )
        self.assertEqual(level, "MEDIUM")

    def test_medium_when_ml_near_miss(self):
        """Score below -0.1 but predict=normal should still return MEDIUM."""
        level = compute_risk_level(
            self._rules(False),
            self._ml(False, -0.15),
        )
        self.assertEqual(level, "MEDIUM")

    def test_low_for_clean_claim(self):
        level = compute_risk_level(
            self._rules(False),
            self._ml(False, 0.3),
        )
        self.assertEqual(level, "LOW")

    def test_low_when_score_exactly_at_threshold(self):
        """Score of exactly -0.1 should NOT trigger the near-miss MEDIUM."""
        level = compute_risk_level(
            self._rules(False),
            self._ml(False, -0.1),
        )
        self.assertEqual(level, "LOW")

    def test_result_is_always_a_valid_string(self):
        for flagged in (True, False):
            for anomaly in (True, False):
                for score in (-1.0, -0.05, 0.3):
                    level = compute_risk_level(
                        self._rules(flagged),
                        self._ml(anomaly, score),
                    )
                    self.assertIn(level, {"HIGH", "MEDIUM", "LOW"})
