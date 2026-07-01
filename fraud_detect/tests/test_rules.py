"""
Unit tests for the rules engine.

Run with:
    docker compose exec backend python manage.py test fraud_detect.tests.test_rules
"""

from datetime import date

from django.test import TestCase

from fraud_detect.rules import evaluate_rules


class RulesEngineTestCase(TestCase):

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_claim(self, **overrides):
        """Returns a clean claim dict with safe defaults, overriding with kwargs."""
        defaults = {
            "claimed_amount": 5000,
            "approved_amount": 5000,
            "date_from": date(2025, 3, 1),
            "date_claimed": date(2025, 3, 3),
            "icd_code": "J06.9",  # Upper respiratory infection — non-vague
            "audit_date": None,
        }
        defaults.update(overrides)
        return defaults

    def _rule_names(self, result):
        return [r["name"] for r in result["fired_rules"]]

    # ------------------------------------------------------------------
    # Baseline — clean claim should never be flagged
    # ------------------------------------------------------------------

    def test_clean_claim_is_not_flagged(self):
        result = evaluate_rules(self._make_claim())
        self.assertFalse(result["is_flagged"])
        self.assertEqual(result["fired_rules"], [])

    # ------------------------------------------------------------------
    # Rule: Claim lag exceeds 90 days
    # ------------------------------------------------------------------

    def test_claim_lag_fires_at_91_days(self):
        claim = self._make_claim(
            date_from=date(2025, 1, 1),
            date_claimed=date(2025, 4, 2),  # 91 days
        )
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])
        self.assertIn("Claim lag exceeds 90 days", self._rule_names(result))

    def test_claim_lag_fires_at_exactly_91_days(self):
        claim = self._make_claim(
            date_from=date(2025, 1, 1),
            date_claimed=date(2025, 4, 2),
        )
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])

    def test_claim_lag_does_not_fire_at_90_days(self):
        claim = self._make_claim(
            date_from=date(2025, 1, 1),
            date_claimed=date(2025, 4, 1),  # exactly 90 days — boundary
        )
        result = evaluate_rules(claim)
        self.assertFalse(result["is_flagged"])

    def test_claim_lag_does_not_fire_when_dates_missing(self):
        claim = self._make_claim(date_from=None, date_claimed=None)
        result = evaluate_rules(claim)
        self.assertFalse(result["is_flagged"])

    # ------------------------------------------------------------------
    # Rule: Invoice inflation above 3x
    # ------------------------------------------------------------------

    def test_inflation_fires_when_invoice_is_above_3x_settled(self):
        # 9001 / 3000 ≈ 3.0003 — just above threshold
        claim = self._make_claim(claimed_amount=9001, approved_amount=3000)
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])
        self.assertIn("Invoice inflation above 3x", self._rule_names(result))

    def test_inflation_does_not_fire_at_exactly_3x(self):
        claim = self._make_claim(claimed_amount=9000, approved_amount=3000)
        result = evaluate_rules(claim)
        # 9000/3000 = 3.0 — not *above* 3.0
        self.assertFalse(result["is_flagged"])

    def test_inflation_does_not_fire_for_zero_approved(self):
        # Division by zero guard — should not crash or false-flag
        claim = self._make_claim(claimed_amount=5000, approved_amount=0)
        result = evaluate_rules(claim)
        self.assertFalse(result["is_flagged"])

    # ------------------------------------------------------------------
    # Rule: Vague ICD code
    # ------------------------------------------------------------------

    def test_vague_icd_fires_for_z519(self):
        result = evaluate_rules(self._make_claim(icd_code="Z51.9"))
        self.assertTrue(result["is_flagged"])
        self.assertIn("Vague ICD code used", self._rule_names(result))

    def test_vague_icd_fires_for_z000(self):
        result = evaluate_rules(self._make_claim(icd_code="Z00.0"))
        self.assertTrue(result["is_flagged"])

    def test_vague_icd_does_not_fire_for_specific_code(self):
        result = evaluate_rules(self._make_claim(icd_code="J18.9"))  # Pneumonia
        self.assertFalse(result["is_flagged"])

    # ------------------------------------------------------------------
    # Rule: Claim filed after audit date
    # ------------------------------------------------------------------

    def test_claim_after_audit_fires(self):
        claim = self._make_claim(
            date_claimed=date(2025, 5, 1),
            audit_date=date(2025, 4, 1),  # audit was before claim
        )
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])
        self.assertIn("Claim filed after audit date", self._rule_names(result))

    def test_claim_before_audit_does_not_fire(self):
        claim = self._make_claim(
            date_claimed=date(2025, 3, 1),
            audit_date=date(2025, 4, 1),
        )
        result = evaluate_rules(claim)
        self.assertFalse(result["is_flagged"])

    def test_audit_date_rule_does_not_fire_when_audit_date_missing(self):
        claim = self._make_claim(audit_date=None)
        result = evaluate_rules(claim)
        self.assertFalse(result["is_flagged"])

    # ------------------------------------------------------------------
    # Rule: High-value claim with vague diagnosis
    # ------------------------------------------------------------------

    def test_high_value_vague_icd_fires(self):
        claim = self._make_claim(claimed_amount=25000, icd_code="Z51.9")
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])
        names = self._rule_names(result)
        self.assertIn("High-value claim with vague diagnosis", names)

    def test_high_value_specific_icd_does_not_fire_high_value_rule(self):
        claim = self._make_claim(claimed_amount=25000, icd_code="J18.9")
        result = evaluate_rules(claim)
        names = self._rule_names(result)
        self.assertNotIn("High-value claim with vague diagnosis", names)

    # ------------------------------------------------------------------
    # Multiple rules firing on the same claim
    # ------------------------------------------------------------------

    def test_multiple_rules_can_fire_simultaneously(self):
        claim = self._make_claim(
            claimed_amount=30000,
            approved_amount=5000,
            icd_code="Z51.9",
            date_from=date(2025, 1, 1),
            date_claimed=date(2025, 6, 1),  # 151 days
        )
        result = evaluate_rules(claim)
        self.assertTrue(result["is_flagged"])
        self.assertGreater(len(result["fired_rules"]), 1)

    # ------------------------------------------------------------------
    # Result structure
    # ------------------------------------------------------------------

    def test_result_always_has_required_keys(self):
        result = evaluate_rules(self._make_claim())
        self.assertIn("is_flagged", result)
        self.assertIn("fired_rules", result)
        self.assertIsInstance(result["is_flagged"], bool)
        self.assertIsInstance(result["fired_rules"], list)

    def test_fired_rule_entries_have_name_and_description(self):
        claim = self._make_claim(icd_code="Z51.9")
        result = evaluate_rules(claim)
        for rule in result["fired_rules"]:
            self.assertIn("name", rule)
            self.assertIn("description", rule)
