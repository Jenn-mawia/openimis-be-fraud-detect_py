"""
Rules engine for the fraud detection module.

Rules are plain Python dicts. Each rule has:
  - name: human-readable label shown to the reviewer
  - description: explanation of why this signals fraud
  - check: a callable(claim_dict) -> bool; True means the rule fired (flag the claim)

A claims dict is expected to have these keys (all optional — missing values degrade
gracefully rather than raising errors):
  - claimed_amount    (float) — the amount the provider invoiced
  - approved_amount   (float) — the amount the insurer approved for payment
  - date_from         (date)  — service start date
  - date_claimed      (date)  — date the claim was submitted
  - audit_date        (date)  — date the claim was audited (if available)
  - icd_code          (str)   — primary ICD-10 diagnosis code

Administrators can tune thresholds by editing the constants at the top of this file.
"""

# ---------------------------------------------------------------------------
# Configurable thresholds — change these to tune rule sensitivity
# ---------------------------------------------------------------------------
CLAIM_LAG_THRESHOLD_DAYS = 90        # days between service and claim submission
INFLATION_RATIO_THRESHOLD = 3.0      # invoice / settled > this is suspicious
HIGH_VALUE_THRESHOLD = 20_000        # KES — claims above this need precise ICD codes

# ICD codes considered "vague" — commonly used to disguise the true diagnosis
VAGUE_ICD_CODES = frozenset([
    "Z51.9",  # Medical care, unspecified
    "Z00.0",  # General medical examination
    "Z76.9",  # Person encountering health services in unspecified circumstances
    "Z71.9",  # Person encountering health services for unspecified counselling
    "Z53.9",  # Procedure not carried out for unspecified reason
])


# ---------------------------------------------------------------------------
# Helper functions (not exposed as rules themselves)
# ---------------------------------------------------------------------------

def _invoice_inflation_ratio(claim):
    """Returns invoice / settled, or 1.0 if amounts are unavailable or zero."""
    settled = claim.get("approved_amount") or claim.get("claimed_amount")
    if not settled or settled == 0:
        return 1.0
    return (claim.get("claimed_amount") or 0) / settled


def _claim_lag_days(claim):
    """Returns days between service start date and claim submission date."""
    service_date = claim.get("date_from")
    claim_date = claim.get("date_claimed")
    if not service_date or not claim_date:
        return 0
    return (claim_date - service_date).days


# ---------------------------------------------------------------------------
# Rules list
# ---------------------------------------------------------------------------

RULES = [
    {
        "name": "Claim lag exceeds 90 days",
        "description": (
            "The claim was filed more than 90 days after the service was delivered. "
            "This is a strong indicator of backdated or fabricated claims."
        ),
        "check": lambda claim: _claim_lag_days(claim) > CLAIM_LAG_THRESHOLD_DAYS,
    },
    {
        "name": "Invoice inflation above 3x",
        "description": (
            "The invoiced amount is more than 3 times the amount that was approved "
            "for payment. This suggests deliberate overbilling."
        ),
        "check": lambda claim: _invoice_inflation_ratio(claim) > INFLATION_RATIO_THRESHOLD,
    },
    {
        "name": "Vague ICD code used",
        "description": (
            "The claim uses a non-specific ICD code (such as Z51.9 — 'medical care, "
            "unspecified') which can be used to disguise the true nature of the visit."
        ),
        "check": lambda claim: claim.get("icd_code") in VAGUE_ICD_CODES,
    },
    {
        "name": "Claim filed after audit date",
        "description": (
            "The claim submission date is after the audit date, which is logically "
            "impossible and suggests record tampering."
        ),
        "check": lambda claim: (
            claim.get("date_claimed") is not None
            and claim.get("audit_date") is not None
            and claim.get("date_claimed") > claim.get("audit_date")
        ),
    },
    {
        "name": "High-value claim with vague diagnosis",
        "description": (
            f"The claimed amount exceeds {HIGH_VALUE_THRESHOLD:,} KES but the "
            "diagnosis code is non-specific. High-value claims require precise "
            "clinical justification."
        ),
        "check": lambda claim: (
            (claim.get("claimed_amount") or 0) > HIGH_VALUE_THRESHOLD
            and claim.get("icd_code") in VAGUE_ICD_CODES
        ),
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def evaluate_rules(claim_dict):
    """
    Runs a claim dictionary through all configured rules.

    Args:
        claim_dict: dict with claim fields (see module docstring for expected keys).

    Returns:
        dict with:
          - is_flagged (bool): True if at least one rule fired.
          - fired_rules (list[dict]): list of {name, description} for each fired rule.
    """
    fired = []
    for rule in RULES:
        try:
            if rule["check"](claim_dict):
                fired.append(
                    {"name": rule["name"], "description": rule["description"]}
                )
        except Exception:
            # A broken rule must never crash claim processing.
            pass

    return {
        "is_flagged": len(fired) > 0,
        "fired_rules": fired,
    }
