from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from backend.app.services.analysis_service import AnalysisService

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> dict:
    return await AnalysisService().analyze(payload.text)
