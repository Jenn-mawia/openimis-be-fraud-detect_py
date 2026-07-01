from django.apps import AppConfig

MODULE_NAME = "fraud_detect"

DEFAULT_CFG = {
    # Minimum anomaly score threshold below which a claim is flagged by ML
    "ml_anomaly_threshold": -0.1,
    # Contamination parameter used when retraining the model
    "model_contamination": 0.08,
    # Permission codes — align with openIMIS permission numbering convention
    "gql_query_fraud_flags_perms": [],
    "gql_mutation_reviewer_override_perms": [],
}


class FraudDetectConfig(AppConfig):
    name = MODULE_NAME
    verbose_name = "Fraud Detection"
    default_auto_field = "django.db.models.AutoField"

    ml_anomaly_threshold = None
    model_contamination = None
    gql_query_fraud_flags_perms = []
    gql_mutation_reviewer_override_perms = []

    def ready(self):
        # Wire up the post_save signal on the Claim model.
        # The import is deferred to avoid circular imports at startup.
        import fraud_detect.signals  # noqa: F401
