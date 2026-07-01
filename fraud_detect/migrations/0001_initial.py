from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="FraudFlag",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("claim_id", models.IntegerField(db_index=True, unique=True)),
                ("is_rule_flagged", models.BooleanField(default=False)),
                (
                    "rule_flag_reasons",
                    models.JSONField(
                        default=list,
                        help_text="List of rule dicts that fired: [{name, description}, ...]",
                    ),
                ),
                (
                    "anomaly_score",
                    models.FloatField(
                        blank=True,
                        help_text=(
                            "Isolation Forest decision_function score. "
                            "More negative = more suspicious."
                        ),
                        null=True,
                    ),
                ),
                ("is_ml_anomaly", models.BooleanField(default=False)),
                (
                    "overall_risk_level",
                    models.CharField(
                        choices=[
                            ("LOW", "Low"),
                            ("MEDIUM", "Medium"),
                            ("HIGH", "High"),
                        ],
                        db_index=True,
                        default="LOW",
                        max_length=10,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "tbl_FraudFlag"},
        ),
        migrations.CreateModel(
            name="ModelVersion",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("version", models.CharField(max_length=50)),
                ("model_file_path", models.CharField(max_length=500)),
                ("scaler_file_path", models.CharField(max_length=500)),
                ("precision_score", models.FloatField(blank=True, null=True)),
                ("recall_score", models.FloatField(blank=True, null=True)),
                ("f1_score", models.FloatField(blank=True, null=True)),
                ("training_date", models.DateTimeField(auto_now_add=True)),
                ("is_active", models.BooleanField(db_index=True, default=False)),
            ],
            options={"db_table": "tbl_FraudModelVersion"},
        ),
        migrations.CreateModel(
            name="ReviewerOverride",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("claim_id", models.IntegerField(db_index=True)),
                (
                    "fraud_flag",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="overrides",
                        to="fraud_detect.fraudflag",
                    ),
                ),
                ("original_risk_level", models.CharField(max_length=10)),
                (
                    "reviewer_decision",
                    models.CharField(
                        choices=[
                            ("APPROVE", "Approve"),
                            ("REJECT", "Reject"),
                            ("ESCALATE", "Escalate"),
                        ],
                        max_length=20,
                    ),
                ),
                ("reviewer_id", models.IntegerField()),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"db_table": "tbl_ReviewerOverride"},
        ),
    ]
