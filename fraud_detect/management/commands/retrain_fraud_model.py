"""
Management command: retrain_fraud_model

Retrains the Isolation Forest model using the base feature dataset, then
records the new model version in the database and marks it as active.

Usage:
    python manage.py retrain_fraud_model
    python manage.py retrain_fraud_model --contamination 0.05
    python manage.py retrain_fraud_model --n-estimators 300 --dry-run

Reviewer overrides are loaded and logged (future: use them to weight training
samples or remove confirmed false-positives from the contamination estimate).
"""

import os

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Retrains the fraud detection Isolation Forest using reviewer feedback."

    def add_arguments(self, parser):
        parser.add_argument(
            "--contamination",
            type=float,
            default=0.08,
            help="Expected fraction of anomalies in the training data (default: 0.08).",
        )
        parser.add_argument(
            "--n-estimators",
            type=int,
            default=200,
            help="Number of trees in the Isolation Forest (default: 200).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Load data and fit the model but do NOT save artefacts or update the DB.",
        )

    def handle(self, *args, **options):
        try:
            import joblib
            import numpy as np
            import pandas as pd
            from sklearn.ensemble import IsolationForest
            from sklearn.preprocessing import StandardScaler
        except ImportError as exc:
            raise CommandError(
                f"Required package not installed: {exc}. "
                "Run: pip install scikit-learn joblib pandas"
            ) from exc

        from fraud_detect.models import ModelVersion, ReviewerOverride

        contamination = options["contamination"]
        n_estimators = options["n_estimators"]
        dry_run = options["dry_run"]

        # ------------------------------------------------------------------
        # 1. Load base feature data
        # ------------------------------------------------------------------
        base_data_path = os.path.normpath(
            os.path.join(
                os.path.dirname(__file__), "..", "..", "..", "data", "claims_features.csv"
            )
        )
        if not os.path.exists(base_data_path):
            raise CommandError(
                f"Feature data not found at {base_data_path}. "
                "Run the Phase 3 training script first or copy claims_features.csv into data/."
            )

        self.stdout.write(f"Loading base feature data from {base_data_path} …")
        df = pd.read_csv(base_data_path)

        feature_columns = [
            "invoice_inflation_ratio",
            "claim_lag_days",
            "icd_is_vague",
            "provider_avg_inflation",
            "provider_claim_count",
            "member_claim_count",
            "amount_vs_benchmark",
        ]

        missing = [c for c in feature_columns if c not in df.columns]
        if missing:
            raise CommandError(
                f"Feature columns missing from CSV: {missing}. "
                "Regenerate claims_features.csv using the Phase 2 script."
            )

        # ------------------------------------------------------------------
        # 2. Log reviewer override statistics
        # ------------------------------------------------------------------
        overrides = ReviewerOverride.objects.filter(
            reviewer_decision="APPROVE",
            original_risk_level__in=["HIGH", "MEDIUM"],
        )
        self.stdout.write(
            f"Reviewer overrides available for feedback: {overrides.count()} "
            "(false-positive corrections)"
        )
        # Future enhancement: remove confirmed FP claim_ids from training set
        # or adjust contamination based on override rate.

        # ------------------------------------------------------------------
        # 3. Fit scaler and model
        # ------------------------------------------------------------------
        X = df[feature_columns].fillna(0)
        self.stdout.write(
            f"Training on {len(X)} rows, contamination={contamination}, "
            f"n_estimators={n_estimators} …"
        )

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = IsolationForest(
            n_estimators=n_estimators,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        model.fit(X_scaled)
        self.stdout.write("Model training complete.")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("Dry run — artefacts NOT saved and DB NOT updated.")
            )
            return

        # ------------------------------------------------------------------
        # 4. Save artefacts
        # ------------------------------------------------------------------
        models_dir = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "models")
        )
        os.makedirs(models_dir, exist_ok=True)

        model_path = os.path.join(models_dir, "fraud_model.joblib")
        scaler_path = os.path.join(models_dir, "fraud_scaler.joblib")

        joblib.dump(model, model_path)
        joblib.dump(scaler, scaler_path)
        self.stdout.write(f"Model saved to {model_path}")
        self.stdout.write(f"Scaler saved to {scaler_path}")

        # Reset cached model in engine so the next request loads the new one.
        import fraud_detect.engine as engine_module
        engine_module._MODEL = None
        engine_module._SCALER = None

        # ------------------------------------------------------------------
        # 5. Record the new model version in the database
        # ------------------------------------------------------------------
        ModelVersion.objects.filter(is_active=True).update(is_active=False)
        new_version = ModelVersion.objects.create(
            version="retrained",
            model_file_path=model_path,
            scaler_file_path=scaler_path,
            is_active=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Model version {new_version.id} recorded and set as active."
            )
        )
