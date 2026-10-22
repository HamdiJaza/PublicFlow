"""Validate the actual generated fields before returning a knowledge answer."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["ROAD_DAMAGE", "STREET_LIGHTING", "WASTE", "WATER_LEAK", "NONE"]


class KnowledgeRequest(BaseModel):
    """The integration contract accepts fixed labels and known prompt files only."""

    model_config = ConfigDict(extra="forbid", strict=True)
    category: Category
    department: str | None = Field(default=None, max_length=200)
    description: str = Field(min_length=1, max_length=3000)
    strategy: Literal["structure", "fixed"] | None = None
    prompt_version: Literal["v3_structured", "v4_grounded", "v5_decision", "v6_roles"] = "v6_roles"


class ModelAnswer(BaseModel):
    """JSON mode alone is insufficient: validate types and refusal consistency too."""

    model_config = ConfigDict(extra="forbid", strict=True)
    procedure: str | None
    deadline: str | None
    answer_found: bool

    @model_validator(mode="after")
    def check_answer(self):
        """A refusal has no procedure/deadline; an answer needs meaningful text."""
        if not self.answer_found and (self.procedure is not None or self.deadline is not None):
            raise ValueError("A refusal requires null procedure and deadline.")
        if self.answer_found and (not self.procedure or self.procedure.strip().lower() in {"", "null", "none"}):
            raise ValueError("answer_found=true requires a nonempty procedure.")
        return self


class SourceItem(BaseModel):
    """A retrieved context source, not a certificate of every generated claim."""

    chunk_id: str
    url: str
    score: float


class KnowledgeResponse(ModelAnswer):
    """Public response fields remain compatible with the original endpoint."""

    sources: list[SourceItem] = Field(default_factory=list)
