"""
Sentinel 舆情分析系统 — Web 看板 (Dashboard)
=============================================
Phase 1 简单看板: 事件列表 + 评级分布 + 基础统计

技术: FastAPI + Jinja2 模板（Phase 1 轻量方案）
后续: 升级为 React SPA
"""
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse


# ============================================================
#  应用实例
# ============================================================

def create_dashboard_app(config: dict) -> FastAPI:
    """
    创建 Dashboard FastAPI 应用

    Args:
        config: 全局配置字典（包含数据库连接等）

    Returns:
        FastAPI: Dashboard 应用实例

    包含的端点:
        GET /                       → 看板主页（HTML）
        GET /api/events             → 事件列表（分页、过滤）
        GET /api/events/{event_id}  → 事件详情
        GET /api/stats              → 统计数据
        GET /api/stats/risk-distribution → 风险分布
        GET /api/stats/source-distribution → 来源分布
        GET /api/graph/stats        → 图谱统计
    """
    ...


# ============================================================
#  页面渲染
# ============================================================

def render_dashboard() -> str:
    """
    渲染看板主页 HTML

    Returns:
        str: HTML 页面内容

    作用:
        使用 Jinja2 模板渲染看板页面
        包含:
            - 顶部统计卡片（总事件数、高评级数、图谱节点数、处理速率）
            - 事件列表表格（分页、按时间倒序）
            - 风险分布饼图（high/medium/low 占比）
            - 来源分布柱状图（news/chat/transaction/behavior）
        Phase 1 使用服务端渲染 + Chart.js CDN
    """
    ...


# ============================================================
#  API 端点处理函数
# ============================================================

async def get_events(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    source: str = Query(None),
    risk_level: str = Query(None),
    event_type: str = Query(None),
    keyword: str = Query(None),
) -> dict:
    """
    获取事件列表（分页 + 多维过滤）

    Args:
        page: 页码（从 1 开始）
        page_size: 每页条数
        source: 按来源过滤 (news/chat/transaction/behavior)
        risk_level: 按风险等级过滤 (high/medium/low)
        event_type: 按事件类型过滤
        keyword: 关键词搜索（模糊匹配 raw_content）

    Returns:
        dict: 分页结果:
            {
                "total": 1523,
                "page": 1,
                "page_size": 20,
                "items": [
                    {
                        "event_id": "...",
                        "source": "news",
                        "event_type": "负面舆情",
                        "risk_level": "high",
                        "risk_score": 0.85,
                        "summary": "...",
                        "timestamp": "...",
                        "key_entities": [...]
                    },
                    ...
                ]
            }

    作用:
        查询 PostgreSQL events 表
        支持多维组合过滤
        按时间倒序排列
    """
    ...


async def get_stats() -> dict:
    """
    获取系统整体统计数据

    Returns:
        dict: 统计数据:
            {
                "total_events": 1523,
                "high_risk_count": 45,
                "medium_risk_count": 312,
                "low_risk_count": 1166,
                "avg_processing_latency_ms": 3200,
                "events_per_minute": 12.5,
                "graph_node_count": 3890,
                "graph_edge_count": 5210,
                "uptime_hours": 48.2
            }

    作用:
        聚合查询 PostgreSQL events 表
        调用 graph_service.get_graph_stats() 获取图谱统计
        计算实时处理速率
    """
    ...


async def get_risk_distribution() -> dict:
    """
    获取风险等级分布数据（用于饼图）

    Returns:
        dict: {"high": 45, "medium": 312, "low": 1166}

    作用:
        SQL GROUP BY risk_level 统计
    """
    ...


async def get_source_distribution() -> dict:
    """
    获取事件来源分布数据（用于柱状图）

    Returns:
        dict: {"news": 523, "chat": 412, "transaction": 301, "behavior": 287}

    作用:
        SQL GROUP BY source 统计
    """
    ...
