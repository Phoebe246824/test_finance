from __future__ import annotations

from fastapi import APIRouter

from backend.app.schemas.analysis import AnalyzeRequest, AnalyzeResponse
from backend.app.services.analysis_service import AnalysisService
from scripts.finance_demo_cases import FINANCE_CASES

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(payload: AnalyzeRequest) -> dict:
    return await AnalysisService().analyze(payload.text)


@router.get("/demo-cases")
async def demo_cases() -> dict:
    return {
        "items": [
            {
                "id": case["id"],
                "title": case["title"],
                "text": case["text"],
                "expect": case.get("expect", []),
            }
            for case in FINANCE_CASES
        ]
    }
