from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.core.security import CurrentUser, require_roles
from backend.app.services.audit_service import write_audit_log
from backend.app.services.risk_rule_service import (
    DEFAULT_RULES,
    load_risk_rules,
    save_risk_rules,
)

router = APIRouter(prefix="/api/risk-rules", tags=["risk-rules"])


class RiskRuleConfig(BaseModel):
    thresholds: dict[str, float] = Field(default_factory=dict)
    dimension_weights: dict[str, float] = Field(default_factory=dict)
    disposal_templates: dict[str, list[str]] = Field(default_factory=dict)


@router.get("")
async def get_risk_rules() -> dict:
    rules, updated_at = load_risk_rules()
    return {"rules": rules, "updated_at": updated_at}


@router.put("")
async def update_risk_rules(
    payload: RiskRuleConfig,
    user: CurrentUser = Depends(require_roles("admin")),
) -> dict:
    rules, updated_at = save_risk_rules(payload.model_dump())
    write_audit_log(
        actor=user,
        action="risk_rules.update",
        resource_type="risk_rule_config",
        resource_id="default",
        detail={"updated_at": updated_at},
    )
    return {"rules": rules, "updated_at": updated_at}
