from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.app.db.session import get_connection
from blacklist.sqlite_store import SQLiteBlacklistStore

router = APIRouter(prefix="/api/blacklist", tags=["blacklist"])
ITEM_TYPE_MAP = {
    "persons": "person",
    "keywords": "keyword",
    "events": "event",
}


PERSON_SEEDS = [
    ("P05", "公共安全测试人员", "旧版演示保留样本。"),
    ("P105", "客户E", "涉诈账户转账、虚拟币保证金、新设备登录金融欺诈样本。"),
]

KEYWORD_SEEDS = [
    ("洗钱", "反洗钱高危关键词", "疑似资金归集、分拆交易或黑钱清洗。"),
    ("反洗钱", "合规复核关键词", "触发 AML 审核与冻结后续出金。"),
    ("分拆交易", "规避阈值交易", "短时间多账户、多笔接近阈值转账。"),
    ("涉诈账户", "涉诈收款方", "被投诉或已标记的疑似诈骗账户。"),
    ("虚拟币", "虚拟币资金通道", "资金进入虚拟币平台或相关商户。"),
    ("保证金", "诱导投资话术", "常见诈骗入金备注。"),
    ("贷款欺诈", "贷款场景欺诈", "包装流水、骗贷相关风险。"),
    ("包装流水", "虚假流水", "贷款欺诈和资质包装风险。"),
    ("冻结", "处置动作", "需要冻结、止付或人工复核。"),
    ("新设备", "设备异常", "首次登录或非常用设备发起交易。"),
    ("境外 IP", "登录地域异常", "跨境或异常网络环境。"),
    ("短信验证码", "账户接管信号", "验证码泄露或被诱导提供。"),
    ("支付通道", "出金路径", "资金快速外流或跑分通道。"),
    ("投诉", "历史投诉信号", "被多名客户投诉诱导投资。"),
    ("返利", "诱导转账话术", "高返利、高收益诱导。"),
    ("刀具", "公共安全风险", "跨领域高危事件样本。"),
    ("可燃液体", "公共安全风险", "跨领域高危事件样本。"),
    ("危险化学品", "公共安全风险", "跨领域高危事件样本。"),
]

EVENT_SEEDS = [
    (
        "E-HIGH-RISK-001",
        "公共安全高危样本",
        "某人员携带刀具与可燃液体进入地下停车场并与他人发生冲突，存在严重公共安全风险。",
    ),
    (
        "E-HIGH-RISK-002",
        "危化品高危样本",
        "仓库内发现大量危险化学品和疑似爆炸装置材料，现场情况紧急，警方和消防已介入。",
    ),
    (
        "E-FIN-AML-001",
        "反洗钱分拆交易样本",
        "客户在短时间内向多个新开户账户转出接近阈值资金，随后资金归集至虚拟币平台，疑似分拆交易与洗钱。",
    ),
    (
        "E-FIN-FRAUD-001",
        "涉诈账户转账样本",
        "客户向曾被投诉的涉诈账户转账虚拟币保证金，交易设备异常且登录地点偏离常驻城市。",
    ),
    (
        "E-FIN-DEVICE-001",
        "异常设备登录样本",
        "客户账户在非常用设备和异常地理位置登录后立即发起大额转账，疑似账户盗用或电诈转账。",
    ),
    (
        "E-FIN-MULE-001",
        "跑分账户样本",
        "多个客户向同一新开户账户集中转账，资金随后快速出金至外部支付通道，疑似跑分或资金归集账户。",
    ),
]


class BlacklistCreate(BaseModel):
    value: str = Field(..., min_length=1)
    summary: str = ""
    description: str = ""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _upsert_item(item_type: str, value: str, summary: str, description: str) -> None:
    now = _now()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO blacklist_items (
                item_type, value, summary, description, enabled, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 1, ?, ?)
            ON CONFLICT(item_type, value) DO UPDATE SET
                summary=excluded.summary,
                description=excluded.description,
                enabled=1,
                updated_at=excluded.updated_at
            """,
            (item_type, value, summary, description, now, now),
        )


def _list_items(item_type: str) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT * FROM blacklist_items
            WHERE item_type = ? AND enabled = 1
            ORDER BY updated_at DESC
            """,
            (item_type,),
        ).fetchall()
    return [dict(row) for row in rows]


def _normalize_item_type(item_type: str) -> str:
    normalized = ITEM_TYPE_MAP.get(item_type)
    if normalized is None:
        raise HTTPException(status_code=404, detail="unknown blacklist type")
    return normalized


async def _ensure_default_items() -> None:
    for value, summary, description in PERSON_SEEDS:
        _upsert_item("person", value, summary, description)
    for value, summary, description in KEYWORD_SEEDS:
        _upsert_item("keyword", value, summary, description)
    for value, summary, description in EVENT_SEEDS:
        _upsert_item("event", value, summary, description)


@router.get("/{item_type}")
async def list_blacklist_items(item_type: str) -> dict:
    normalized = _normalize_item_type(item_type)
    await _ensure_default_items()
    return {"items": _list_items(normalized)}


@router.post("/{item_type}")
async def create_blacklist_item(item_type: str, payload: BlacklistCreate) -> dict:
    normalized = _normalize_item_type(item_type)
    _upsert_item(normalized, payload.value, payload.summary, payload.description)
    return {"created": True, "item_type": normalized, "value": payload.value}


@router.delete("/{item_type}/{value}")
async def delete_blacklist_item(item_type: str, value: str) -> dict:
    normalized = _normalize_item_type(item_type)
    store = SQLiteBlacklistStore(get_connection)
    removed = await {
        "person": store.remove_person,
        "keyword": store.remove_keyword,
        "event": store.remove_event,
    }[normalized](value)
    if not removed:
        raise HTTPException(status_code=404, detail="blacklist item not found")
    return {"deleted": True, "item_type": normalized, "value": value}
