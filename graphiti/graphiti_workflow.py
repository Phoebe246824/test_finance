import asyncio
import json
import os
import sys
from datetime import datetime, date
from enum import Enum
from typing import Any, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.cross_encoder.bge_reranker_client import BGERerankerClient
from graphiti_core.prompts import Message
from graphiti_core.search.search_config_recipes import COMBINED_HYBRID_SEARCH_CROSS_ENCODER, COMBINED_HYBRID_SEARCH_RRF
from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient


load_dotenv()


# ========================
# Config
# ========================

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
OPENAI_API_KEY = os.environ.get("LLM_API_KEY")

if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
    raise ValueError("NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set")

if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY must be set")


# ========================
# Pydantic schema models
# ========================

class Event(BaseModel):
    event_id: Optional[str] = Field(None, description="事件编号，如 E1、E2")
    event_date: Optional[date] = Field(None, description="事件发生日期")
    location: Optional[str] = Field(None, description="事件发生地点")
    event_type: Optional[str] = Field(None, description="事件类型")
    severity: Optional[str] = Field(None, description="事件严重程度")
    key_metric: Optional[str] = Field(None, description="关键指标及数值")
    source: Optional[str] = Field(None, description="信息来源机构")


class Organization(BaseModel):
    org_name: Optional[str] = Field(None, description="组织全称")
    org_type: Optional[str] = Field(None, description="组织类型")
    country: Optional[str] = Field(None, description="所属国家或地区")
    role: Optional[str] = Field(None, description="在本事件中的角色")
    impact: Optional[str] = Field(None, description="影响描述")


class Commodity(BaseModel):
    commodity_name: Optional[str] = Field(None, description="商品名称")
    unit: Optional[str] = Field(None, description="计价单位")
    price_before: Optional[float] = Field(None, description="事件前价格")
    price_after: Optional[float] = Field(None, description="事件后价格")
    change_percent: Optional[float] = Field(None, description="价格变动百分比")
    supply_impact: Optional[str] = Field(None, description="供给端影响")
    demand_impact: Optional[str] = Field(None, description="需求端影响")


class Technology(BaseModel):
    tech_name: Optional[str] = Field(None, description="技术名称")
    category: Optional[str] = Field(None, description="技术类别")
    maturity: Optional[str] = Field(None, description="成熟度阶段")
    energy_density: Optional[str] = Field(None, description="能量密度")
    key_parameter: Optional[str] = Field(None, description="关键参数")
    is_disruptive: Optional[bool] = Field(None, description="是否为颠覆性技术")


class Policy(BaseModel):
    policy_name: Optional[str] = Field(None, description="政策名称")
    policy_type: Optional[str] = Field(None, description="政策类型")
    issuer: Optional[str] = Field(None, description="发布主体")
    target: Optional[str] = Field(None, description="政策目标对象")
    effective_date: Optional[date] = Field(None, description="生效日期")
    key_rate: Optional[str] = Field(None, description="关键税率/金额/比例")


class Causes(BaseModel):
    mechanism: Optional[str] = Field(None, description="因果传导机制")
    confidence: Optional[str] = Field(None, description="因果置信度")
    time_lag: Optional[str] = Field(None, description="因果时间差")
    evidence: Optional[str] = Field(None, description="证据摘要")


class Involves(BaseModel):
    role: Optional[str] = Field(None, description="实体角色")
    involvement_type: Optional[str] = Field(None, description="参与类型")
    importance: Optional[str] = Field(None, description="重要程度")

# ========================
# Client factory / workflow helpers
# ========================

async def init_graph_client(config: dict) -> Graphiti:
    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=OPENAI_API_KEY,
            model="deepseek-ai/DeepSeek-V3.2",
            base_url="https://api.siliconflow.cn/v1",
        )
    )

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model="BAAI/bge-m3",
            api_key=OPENAI_API_KEY,
            base_url="https://api.siliconflow.cn/v1",
        )
    )
    cross_encoder=OpenAIRerankerClient(
        config=LLMConfig(
            api_key=os.environ.get('OPENAI_API_KEY'),
            base_url='https://api.siliconflow.cn/v1',
            model="Pro/BAAI/bge-reranker-v2-m3"
        )
    )
    graphiti = Graphiti(
        NEO4J_URI,
        NEO4J_USER,
        NEO4J_PASSWORD,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
    )

    await graphiti.build_indices_and_constraints()
    return graphiti


async def close_graph_client(graphiti: Graphiti) -> None:
    await graphiti.close()


async def _summarize_for_extraction(
    graphiti: Graphiti,
    text: str,
    source_description: str,
) -> str:
    llm_client = graphiti.llm_client
    return await summarize_text(llm_client, source_description, text)


async def add_event_to_graph(
    graphiti: Graphiti,
    event_text: str,
    reference_time: datetime | None = None,
    source_description: str | None = None,
    group_id: str = "message_record",
    custom_extraction_instructions: str | None = None,
    update_communities: bool = False,
    summarize_before_extract: bool = False, #是否先摘要再抽取
) -> Any:
    effective_reference_time = reference_time or datetime.now()
    effective_source = source_description or "工作流输入"
    entity_types = {
        "Event": Event,
        "Organization": Organization,
        "Commodity": Commodity,
        "Technology": Technology,
        "Policy": Policy,
    }

    edge_types = {
        "Causes": Causes,
        "Involves": Involves,
    }

    edge_type_map = {
        ("Event", "Event"): ["Causes"],
        ("Event", "Organization"): ["Involves"],
        ("Event", "Commodity"): ["Involves"],
        ("Event", "Technology"): ["Involves"],
        ("Event", "Policy"): ["Involves"],
        ("Organization", "Technology"): ["Involves"],
        ("Policy", "Organization"): ["Involves"],
        ("Commodity", "Organization"): ["Involves"],
        ("Entity", "Entity"): ["Involves"],
    }
    default_custom_instructions = (
        "请优先基于输入摘要抽取清晰、规范的事件节点，事件名必须尽量是“主体+动作/结果”的形式。"
        "用户输入原文只作为补充证据，不要优先围绕碎片抽取。"
        "只有在事件节点已明确抽出后，才抽取因果边 Causes。"
        "如果一段输入里隐含多个事件，请拆成多个事件节点再建立因果链。"
        "自定义关系抽取逻辑保持不变，仍然优先抽取事件间因果与参与关系。"
    )
    effective_event_text = event_text
    summary_text = None

    if summarize_before_extract:
        summary_text = await _summarize_for_extraction(graphiti, event_text, effective_source)
        effective_event_text = summary_text

    result = await graphiti.add_episode(
        name=effective_source,
        episode_body=effective_event_text,
        source_description=effective_source,
        reference_time=effective_reference_time,
        entity_types=entity_types,
        edge_types=edge_types,
        edge_type_map=edge_type_map,
        custom_extraction_instructions=custom_extraction_instructions or default_custom_instructions,
        group_id=group_id,
        update_communities=update_communities,
    )

    result_payload = (
        result.model_dump()
        if hasattr(result, "model_dump")
        else result.dict()
        if hasattr(result, "dict")
        else result
    )

    entities_extracted = len(result_payload.get("nodes", []))
    relations_created = len(result_payload.get("edges", []))

    return {
        "entities_extracted": entities_extracted,
        "relations_created": relations_created,
        "input_text": event_text,
        "summary": summary_text,
        "used_summary_for_extraction": summarize_before_extract,
        "group_id":group_id
    }


async def hybrid_search(
    graphiti: Graphiti,
    query: str,
    group_id: str | None = None,
    num_results: int = 10,
    recipe: Any = COMBINED_HYBRID_SEARCH_RRF,#默认
    filters: Any | None = None,
) -> Any:
    group_ids = [group_id] if group_id else None
    result = await graphiti.search_(
        query,
        config=recipe,
        group_ids=group_ids,
        search_filter=filters,
    )
    return {
        "query": query,
        "edges": result.edges,
        "nodes": result.nodes,
        "episodes": result.episodes,
        "communities": result.communities,
        "total": len(result.edges) + len(result.nodes) + len(result.episodes) + len(result.communities)
    }



async def summarize_text(llm_client, title: str, content: str) -> str:
    system_prompt = (
        "你是严谨的信息压缩助手。请从原文中提炼最重要、最稳定、最适合后续实体抽取与关系抽取的事实。"
        "去掉重复、修饰、情绪化表达和弱相关细节，只保留关键事件、主体、动作、结果、数字、时间、地点、因果关系。"
        "输出必须是中文摘要，尽量用条目式。"
    )
    user_prompt = f"""
标题：
{title}

原文：
{content}

请输出一个适合后续 LLM 实体抽取和关系抽取的“重要事实摘要”，要求：
1. 只保留核心事实，不要复述全文。
2. 保留明确时间、地点、主体、动作、结果、数值、因果链。
3. 如有多条关键事实，请用编号列表输出。
4. 控制在 200~400 字左右。
"""
    response = await llm_client.generate_response(
        [
            Message(role="system", content=system_prompt),
            Message(role="user", content=user_prompt),
        ],
        prompt_name="graphiti.workflow.summarize",
    )
    if isinstance(response, str):
        return response.strip()
    if isinstance(response, dict):
        for key in ("answer", "content", "text", "summary"):
            value = response.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return str(response).strip()


