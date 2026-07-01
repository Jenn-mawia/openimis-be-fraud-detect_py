"""
FHIR R4 extension helpers for the fraud detection module (Phase 5).

The openIMIS FHIR R4 module converts claims to FHIR Claim / ClaimResponse
resources.  This file provides the extension objects that inject the fraud
score and risk level into a ClaimResponse resource.

Usage (inside the ClaimResponse converter in the FHIR module):

    from fraud_detect.fhir_extensions import build_fraud_extensions
    from fraud_detect.models import FraudFlag

    flag = FraudFlag.objects.filter(claim_id=claim.id).first()
    fhir_claim_response["extension"] = build_fraud_extensions(flag)

These extension URLs follow the openIMIS namespace convention.
"""

# ---------------------------------------------------------------------------
# Extension URL constants
# ---------------------------------------------------------------------------

FRAUD_SCORE_EXTENSION_URL = (
    "https://openimis.org/fhir/StructureDefinition/fraud-anomaly-score"
)
FRAUD_RISK_LEVEL_EXTENSION_URL = (
    "https://openimis.org/fhir/StructureDefinition/fraud-risk-level"
)
FRAUD_RULES_FIRED_EXTENSION_URL = (
    "https://openimis.org/fhir/StructureDefinition/fraud-rules-fired"
)
FRAUD_ML_ANOMALY_EXTENSION_URL = (
    "https://openimis.org/fhir/StructureDefinition/fraud-ml-anomaly"
)


# ---------------------------------------------------------------------------
# Builder function
# ---------------------------------------------------------------------------

def build_fraud_extensions(fraud_flag):
    """
    Builds a list of FHIR R4 extension dicts from a FraudFlag instance.

    Args:
        fraud_flag: FraudFlag model instance, or None if no flag exists.

    Returns:
        list of FHIR extension dicts (may be empty if fraud_flag is None).
    """
    if not fraud_flag:
        return []

    rules_summary = (
        "; ".join(r["name"] for r in fraud_flag.rule_flag_reasons)
        if fraud_flag.rule_flag_reasons
        else "None"
    )

    extensions = [
        {
            "url": FRAUD_RISK_LEVEL_EXTENSION_URL,
            "valueString": fraud_flag.overall_risk_level,
        },
        {
            "url": FRAUD_ML_ANOMALY_EXTENSION_URL,
            "valueBoolean": fraud_flag.is_ml_anomaly,
        },
        {
            "url": FRAUD_RULES_FIRED_EXTENSION_URL,
            "valueString": rules_summary,
        },
    ]

    # Only include the anomaly score when it has been computed
    if fraud_flag.anomaly_score is not None:
        extensions.insert(0, {
            "url": FRAUD_SCORE_EXTENSION_URL,
            "valueDecimal": round(fraud_flag.anomaly_score, 4),
        })

    return extensions
