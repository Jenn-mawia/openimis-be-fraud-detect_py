"""
Management command: seed_demo_claims

Creates a small set of synthetic Claim records designed to demonstrate
the fraud detection module during the hackathon demo.

  Claim A — clean lab test  → LOW risk
  Claim B — vague ICD + 120-day lag + high invoice  → HIGH risk
  Claim C — invoice inflation (billed 25k, settled 3k)  → MEDIUM/HIGH risk
  Claim D — normal spectacle frame claim  → LOW risk

Usage:
    python manage.py seed_demo_claims
    python manage.py seed_demo_claims --clear  # removes previous demo claims first

NOTE: This command requires the full openIMIS claim/insuree/location/medical
stack to be installed and migrated.  It is safe to run multiple times (it
checks for existing demo claims before creating new ones).
"""

from django.core.management.base import BaseCommand


DEMO_CLAIM_CODES = ["DEMO-A", "DEMO-B", "DEMO-C", "DEMO-D"]


class Command(BaseCommand):
    help = "Seeds demo claim records to showcase the fraud detection module."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing demo claims before seeding new ones.",
        )

    def handle(self, *args, **options):
        try:
            from claim.models import Claim
            from datetime import date, timedelta
        except ImportError:
            self.stderr.write(
                self.style.ERROR(
                    "claim.models could not be imported. "
                    "Ensure the openimis-be-claim module is installed."
                )
            )
            return

        if options["clear"]:
            deleted, _ = Claim.objects.filter(code__in=DEMO_CLAIM_CODES).delete()
            self.stdout.write(f"Cleared {deleted} existing demo claim(s).")

        # Resolve a usable health facility, insuree, and ICD code.
        # These are required FK fields on the Claim model.
        try:
            from location.models import HealthFacility
            from insuree.models import Insuree
            from medical.models import Diagnosis

            hf = HealthFacility.objects.filter(validity_to__isnull=True).first()
            insuree = Insuree.objects.filter(validity_to__isnull=True).first()

            if not hf or not insuree:
                self.stderr.write(
                    self.style.ERROR(
                        "No valid HealthFacility or Insuree found. "
                        "Run the standard openIMIS fixtures first."
                    )
                )
                return

            icd_normal = Diagnosis.objects.filter(code="J06.9").first()
            icd_vague = Diagnosis.objects.filter(code="Z51.9").first()
            icd_spectacle = Diagnosis.objects.filter(code="H52.1").first()

            # Fall back to any available diagnosis if specific codes are missing
            fallback_icd = Diagnosis.objects.filter(validity_to__isnull=True).first()
            icd_normal = icd_normal or fallback_icd
            icd_vague = icd_vague or fallback_icd
            icd_spectacle = icd_spectacle or fallback_icd

        except Exception as exc:
            self.stderr.write(
                self.style.ERROR(f"Could not resolve required FK objects: {exc}")
            )
            return

        today = date.today()

        demo_specs = [
            {
                "code": "DEMO-A",
                "description": "Clean lab test — expected LOW risk",
                "claimed": 3000,
                "approved": 3000,
                "date_from": today - timedelta(days=2),
                "date_claimed": today,
                "icd": icd_normal,
            },
            {
                "code": "DEMO-B",
                "description": "Vague ICD + 120-day lag + high invoice — expected HIGH risk",
                "claimed": 18000,
                "approved": 4000,
                "date_from": today - timedelta(days=120),
                "date_claimed": today,
                "icd": icd_vague,
            },
            {
                "code": "DEMO-C",
                "description": "Invoice inflation 25k vs 3k — expected MEDIUM/HIGH risk",
                "claimed": 25000,
                "approved": 3000,
                "date_from": today - timedelta(days=5),
                "date_claimed": today,
                "icd": icd_normal,
            },
            {
                "code": "DEMO-D",
                "description": "Normal spectacle frame — expected LOW risk",
                "claimed": 4500,
                "approved": 4500,
                "date_from": today - timedelta(days=3),
                "date_claimed": today,
                "icd": icd_spectacle,
            },
        ]

        created_count = 0
        for spec in demo_specs:
            if Claim.objects.filter(code=spec["code"]).exists():
                self.stdout.write(f"  Skipping {spec['code']} — already exists.")
                continue

            try:
                Claim.objects.create(
                    code=spec["code"],
                    claimed=spec["claimed"],
                    approved=spec["approved"],
                    date_from=spec["date_from"],
                    date_to=spec["date_from"],
                    date_claimed=spec["date_claimed"],
                    icd=spec["icd"],
                    insuree=insuree,
                    health_facility=hf,
                    status=2,          # Entered
                    audit_user_id=-1,  # system
                    feedback_available=False,
                    feedback_status=1,
                    review_status=1,
                    approval_status=1,
                    rejection_reason=0,
                )
                self.stdout.write(
                    self.style.SUCCESS(
                        f"  Created {spec['code']}: {spec['description']}"
                    )
                )
                created_count += 1
            except Exception as exc:
                self.stderr.write(
                    self.style.ERROR(f"  Failed to create {spec['code']}: {exc}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Done. Created {created_count} demo claim(s).")
        )
