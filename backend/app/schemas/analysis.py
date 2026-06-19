from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    text: str = Field(..., min_length=1)


class AnalyzeResponse(BaseModel):
    event_id: str
    status: str
    risk_level: str | None = None
    risk_score: float | None = None
    event_type: str | None = None
    summary: str | None = None
    reasoning: str | None = None
    raw_content: str | None = None
    title: str | None = None
    dimension_scores: dict = Field(default_factory=dict)
    trend_report: dict = Field(default_factory=dict)
    blacklist: dict = Field(default_factory=dict)
    graph_result: dict | None = None
    second_risk_applied: bool = False
