"""
Pydantic models for Alert Triage Evaluation API responses.
"""
from typing import List, Optional

from pydantic import BaseModel, Field


class ScoreCriteriaCard(BaseModel):
    """Individual criteria and its percentage score."""
    title: str = Field(description="Title of the evaluation criteria")
    score_percent: float = Field(ge=0, le=100, description="Score for this criteria as a percentage")
    description: str = Field(description="Description of the evaluation criteria")


class TriageEvaluationResponse(BaseModel):
    """Response model for alert triage evaluation endpoint."""
    average_score_percent: float = Field(ge=0, le=100, description="Average evaluation score as a percentage")
    reason: str = Field(description="Reasoning for the average score")
    score_criteria_cards: List[ScoreCriteriaCard] = Field(description="Breakdown of scores by criteria (percentages)")
    status: Optional[str] = Field(default=None, description="Evaluation status: pending, queued, processing, success, error")
