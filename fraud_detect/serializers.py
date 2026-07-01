from rest_framework import serializers

from .models import FraudFlag, ReviewerOverride


class FraudFlagSerializer(serializers.ModelSerializer):
    class Meta:
        model = FraudFlag
        fields = [
            "id",
            "claim_id",
            "is_rule_flagged",
            "rule_flag_reasons",
            "anomaly_score",
            "is_ml_anomaly",
            "overall_risk_level",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReviewerOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewerOverride
        fields = [
            "id",
            "claim_id",
            "original_risk_level",
            "reviewer_decision",
            "reviewer_id",
            "notes",
            "created_at",
        ]
        read_only_fields = ["id", "original_risk_level", "created_at"]

    def validate_reviewer_decision(self, value):
        allowed = {"APPROVE", "REJECT", "ESCALATE"}
        if value not in allowed:
            raise serializers.ValidationError(
                f"reviewer_decision must be one of: {', '.join(sorted(allowed))}"
            )
        return value
