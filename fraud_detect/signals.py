"""
Django signal handlers for the fraud detection module.

Connects to the Claim model's post_save signal so that every claim save
(new or updated) automatically triggers a fraud risk assessment.

The signal handler is intentionally lightweight: it builds the claim dict,
delegates all heavy logic to engine.py / rules.py, and persists the result.
Errors are caught and logged so that a broken fraud engine never blocks a
legitimate claim save.
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deferred imports — resolved at signal-connection time (inside ready()) to
# avoid circular imports during Django startup.
# ---------------------------------------------------------------------------
try:
    from claim.models import Claim
except ImportError:
    # The claim module is not installed in this environment (e.g. unit tests
    # that do not load the full openIMIS stack).  Gracefully skip registration.
    Claim = None

from .engine import compute_risk_level, score_claim_ml
from .models import FraudFlag
from .rules import evaluate_rules


def _build_claim_dict(instance):
    """
    Converts a Claim model instance into the dict format expected by rules.py
    and engine.py.  Maps openIMIS field names to the engine's internal keys.
    """
    return {
        "claimed_amount": float(instance.claimed or 0),
        "approved_amount": float(instance.approved or 0),
        # date_from is the service start date; date_claimed is when the claim
        # was submitted to the insurer.
        "date_from": instance.date_from,
        "date_claimed": instance.date_claimed,
        # Primary ICD-10 diagnosis code (icd is a FK to medical.Diagnosis)
        "icd_code": instance.icd.code if instance.icd else None,
        # audit_date is not a standard Claim field in all openIMIS versions;
        # use validity_from as a proxy when present.
        "audit_date": getattr(instance, "validity_from", None),
        # Provider- and member-level aggregate features are not available on
        # a single Claim instance.  They default to neutral values inside
        # engine.py._extract_features() until a pre-computation step is wired.
    }


def _connect_signals():
    """
    Registers the post_save handler.  Called from FraudDetectConfig.ready().
    Factored out so it can be called explicitly in tests.
    """
    if Claim is None:
        logger.warning(
            "fraud_detect.signals: claim.models.Claim could not be imported. "
            "Signal handler will not be registered."
        )
        return

    post_save.connect(evaluate_claim_on_save, sender=Claim)
    logger.debug("fraud_detect: post_save signal connected to Claim model.")


def _disconnect_signals():
    """Disconnects the signal handler (useful in tests to avoid side-effects)."""
    if Claim is not None:
        post_save.disconnect(evaluate_claim_on_save, sender=Claim)


if Claim is not None:
    @receiver(post_save, sender=Claim)
    def evaluate_claim_on_save(sender, instance, created, **kwargs):
        """
        Automatically assesses a claim for fraud risk after every save.

        Fires for both newly created claims (created=True) and updates
        (created=False, e.g. when a claim is approved/rejected).
        """
        try:
            claim_dict = _build_claim_dict(instance)
            rules_result = evaluate_rules(claim_dict)
            ml_result = score_claim_ml(claim_dict)
            risk_level = compute_risk_level(rules_result, ml_result)

            FraudFlag.objects.update_or_create(
                claim_id=instance.id,
                defaults={
                    "is_rule_flagged": rules_result["is_flagged"],
                    "rule_flag_reasons": rules_result["fired_rules"],
                    "anomaly_score": ml_result["anomaly_score"],
                    "is_ml_anomaly": ml_result["is_anomaly"],
                    "overall_risk_level": risk_level,
                },
            )
        except Exception:
            logger.exception(
                "fraud_detect: Error evaluating claim id=%s. "
                "The claim was saved normally; only fraud scoring failed.",
                getattr(instance, "id", "unknown"),
            )
