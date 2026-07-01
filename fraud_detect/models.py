from django.db import models


class FraudFlag(models.Model):
    """
    Stores the fraud risk assessment for a single claim.
    One row is created (or updated) each time a claim is saved.
    """
    claim_id = models.IntegerField(unique=True, db_index=True)

    # Rules engine output
    is_rule_flagged = models.BooleanField(default=False)
    rule_flag_reasons = models.JSONField(
        default=list,
        help_text="List of rule dicts that fired: [{name, description}, ...]",
    )

    # ML model output
    anomaly_score = models.FloatField(
        null=True,
        blank=True,
        help_text="Isolation Forest decision_function score. More negative = more suspicious.",
    )
    is_ml_anomaly = models.BooleanField(default=False)

    # Combined assessment
    overall_risk_level = models.CharField(
        max_length=10,
        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High")],
        default="LOW",
        db_index=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "tbl_FraudFlag"

    def __str__(self):
        return f"FraudFlag(claim_id={self.claim_id}, risk={self.overall_risk_level})"


class ReviewerOverride(models.Model):
    """
    Records when a human reviewer disagrees with the model's assessment.
    These records feed back into the retraining pipeline (Phase 6).
    """
    claim_id = models.IntegerField(db_index=True)
    fraud_flag = models.ForeignKey(
        FraudFlag,
        on_delete=models.CASCADE,
        related_name="overrides",
    )
    original_risk_level = models.CharField(max_length=10)
    reviewer_decision = models.CharField(
        max_length=20,
        choices=[
            ("APPROVE", "Approve"),
            ("REJECT", "Reject"),
            ("ESCALATE", "Escalate"),
        ],
    )
    reviewer_id = models.IntegerField()
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "tbl_ReviewerOverride"

    def __str__(self):
        return (
            f"ReviewerOverride(claim_id={self.claim_id}, "
            f"decision={self.reviewer_decision})"
        )


class ModelVersion(models.Model):
    """
    Tracks which version of the ML model artefacts are currently active.
    Only one row should have is_active=True at a time.
    """
    version = models.CharField(max_length=50)
    model_file_path = models.CharField(max_length=500)
    scaler_file_path = models.CharField(max_length=500)
    precision_score = models.FloatField(null=True, blank=True)
    recall_score = models.FloatField(null=True, blank=True)
    f1_score = models.FloatField(null=True, blank=True)
    training_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "tbl_FraudModelVersion"

    def __str__(self):
        return f"ModelVersion(version={self.version}, active={self.is_active})"
