"""Check that a model response contains the expected fields and allowed values."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["ROAD_DAMAGE", "STREET_LIGHTING", "WASTE", "WATER_LEAK", "NONE"]


class VisionObservation(BaseModel):
    """One image observation. Unknown values are stored as null in the JSON file."""

    # Reject extra fields and incorrect types instead of silently changing them.
    model_config = ConfigDict(extra="forbid", strict=True)

    category: Category | None
    severity: Literal["LOW", "MEDIUM", "HIGH"] | None
    description: str = Field(min_length=1, max_length=600)
    evidence: list[str] = Field(max_length=6)
    text_image_consistent: bool | None  # None when no report text was supplied.
    # This is the model's estimate, not a measured probability of being correct.
    confidence: float | None = Field(ge=0, le=1)
    uncertainty_reason: str | None

    @model_validator(mode="after")
    def check_uncertain_result(self):
        """Require an explanation for uncertainty and avoid severity without a category."""
        if self.category in (None, "NONE") and self.severity is not None:
            raise ValueError("An unknown or out-of-scope category cannot have severity.")
        if self.category is None and not (self.uncertainty_reason or "").strip():
            raise ValueError("An unknown category needs an uncertainty reason.")
        return self


class VisionEvidence(BaseModel):
    """V5's intermediate visible conditions; these are model claims, not labels."""

    model_config = ConfigDict(extra="forbid", strict=True)

    scene: str = Field(min_length=1, max_length=600)
    waste: str | None
    road: str | None
    water: str | None
    electrical: str | None
    limitations: list[str] = Field(max_length=6)


class VisionDecision(VisionObservation):
    """Keep unvalidated priority and confidence out of v5's final response."""

    severity: None
    confidence: None


class VisionDecisionWithoutText(VisionDecision):
    """A text/image comparison is unavailable when no citizen text was supplied."""

    text_image_consistent: None


class CaptionComparison(BaseModel):
    """V9's text-only judgment of the caption against recorded visual observations."""

    model_config = ConfigDict(extra="forbid", strict=True)

    decision: Literal["NO_CLAIM", "UNVERIFIABLE", "SUPPORTED", "CONTRADICTED"]
    reason: str | None

    @model_validator(mode="after")
    def require_inconclusive_reason(self):
        """A non-checkable caption needs an explanation, not a guessed boolean."""
        if self.decision in ("NO_CLAIM", "UNVERIFIABLE") and not (self.reason or "").strip():
            raise ValueError("A non-checkable caption needs a reason.")
        return self


class CaptionClaim(BaseModel):
    """V11 separates a caption's positive condition from its explicit denial."""

    model_config = ConfigDict(extra="forbid", strict=True)
    kind: Literal["NO_CLAIM", "CLAIM", "UNVERIFIABLE"]
    condition: str | None
    negated: bool
    reason: str | None

    @model_validator(mode="after")
    def check_claim(self):
        """Require a checkable condition or a reason for withholding judgment."""
        if self.kind == "CLAIM":
            if not (self.condition or "").strip():
                raise ValueError("A claim needs a positive condition to check.")
        elif self.condition is not None or self.negated or not (self.reason or "").strip():
            raise ValueError("Non-claims need a reason, null condition and false negation.")
        return self


class VisualCondition(BaseModel):
    """V11's visual check; absence requires a sufficiently clear view."""

    model_config = ConfigDict(extra="forbid", strict=True)
    presence: Literal["PRESENT", "ABSENT", "UNVERIFIABLE"]
    reason: str | None

    @model_validator(mode="after")
    def require_limitation(self):
        """Explain why a condition cannot be verified."""
        if self.presence == "UNVERIFIABLE" and not (self.reason or "").strip():
            raise ValueError("An unverifiable visual condition needs a reason.")
        return self
