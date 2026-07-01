"""
GraphQL schema for the fraud detection module.

Exposes:
  - Query.fraudFlag(claimId)   — fetch the FraudFlag for one claim
  - Query.fraudFlags(...)      — paginated list of FraudFlag records
  - Mutation.reviewerOverride  — record a reviewer's override decision

The schema is automatically merged into the global openIMIS GraphQL schema
by the core module when 'fraud_detect' appears in openimis.json.
"""

import graphene
from graphene_django import DjangoObjectType

from .models import FraudFlag, ReviewerOverride


# ---------------------------------------------------------------------------
# Object types
# ---------------------------------------------------------------------------

class FraudFlagType(DjangoObjectType):
    class Meta:
        model = FraudFlag
        fields = "__all__"


class ReviewerOverrideType(DjangoObjectType):
    class Meta:
        model = ReviewerOverride
        fields = "__all__"


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------

class Query(graphene.ObjectType):

    fraud_flag = graphene.Field(
        FraudFlagType,
        claim_id=graphene.Int(required=True),
        description="Fetch the fraud assessment for a specific claim.",
    )

    fraud_flags = graphene.List(
        FraudFlagType,
        risk_level=graphene.String(
            description="Filter by risk level: HIGH, MEDIUM, or LOW."
        ),
        first=graphene.Int(description="Limit the number of results returned."),
        skip=graphene.Int(description="Number of results to skip (offset)."),
        description="List fraud flags, optionally filtered and paginated.",
    )

    reviewer_overrides = graphene.List(
        ReviewerOverrideType,
        claim_id=graphene.Int(description="Filter overrides for a specific claim."),
        description="List reviewer override decisions.",
    )

    def resolve_fraud_flag(self, info, claim_id):
        return FraudFlag.objects.filter(claim_id=claim_id).first()

    def resolve_fraud_flags(self, info, risk_level=None, first=None, skip=None):
        qs = FraudFlag.objects.all().order_by("-created_at")
        if risk_level:
            qs = qs.filter(overall_risk_level=risk_level)
        if skip:
            qs = qs[skip:]
        if first:
            qs = qs[:first]
        return qs

    def resolve_reviewer_overrides(self, info, claim_id=None):
        qs = ReviewerOverride.objects.all().order_by("-created_at")
        if claim_id is not None:
            qs = qs.filter(claim_id=claim_id)
        return qs


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------

class CreateReviewerOverride(graphene.Mutation):
    """
    Records a reviewer's override decision for a flagged claim.
    """

    class Arguments:
        claim_id = graphene.Int(required=True)
        reviewer_decision = graphene.String(required=True)
        reviewer_id = graphene.Int(required=True)
        notes = graphene.String()

    override = graphene.Field(ReviewerOverrideType)
    ok = graphene.Boolean()

    def mutate(self, info, claim_id, reviewer_decision, reviewer_id, notes=""):
        flag = FraudFlag.objects.filter(claim_id=claim_id).first()
        if not flag:
            return CreateReviewerOverride(ok=False, override=None)

        override = ReviewerOverride.objects.create(
            claim_id=claim_id,
            fraud_flag=flag,
            original_risk_level=flag.overall_risk_level,
            reviewer_decision=reviewer_decision,
            reviewer_id=reviewer_id,
            notes=notes,
        )
        return CreateReviewerOverride(ok=True, override=override)


class Mutation(graphene.ObjectType):
    reviewer_override = CreateReviewerOverride.Field()
