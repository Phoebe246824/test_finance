import logging
import os
from datetime import datetime, date
from typing import Any, List, Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from graphiti_core import Graphiti
from graphiti_core.driver.neo4j_driver import Neo4jDriver
from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig
from graphiti_core.llm_client import LLMConfig
from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
from graphiti_core.cross_encoder.jina_reranker_client import JinaRerankerClient
from graphiti_core.prompts import Message
from graphiti_core.search.search_config_recipes import (
    COMBINED_HYBRID_SEARCH_CROSS_ENCODER,
)
from graphiti_core.search.search_filters import SearchFilters

logger = logging.getLogger(__name__)

ENV_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
load_dotenv(dotenv_path=ENV_PATH, override=True)


# ========================
# Config
# ========================

NEO4J_URI = os.environ.get("NEO4J_URI") or "bolt://localhost:7687"
NEO4J_USER = os.environ.get("NEO4J_USER") or "neo4j"
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD") or "password"
LLM_API_KEY = os.environ.get("LLM_API_KEY")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
LLM_MODEL = os.environ.get("LLM_MODEL") or "gpt-4o"

EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY") or LLM_API_KEY
EMBEDDER_API_BASE = os.environ.get("EMBEDDER_API_BASE") or LLM_BASE_URL
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL") or "BAAI/bge-m3"

RERANKER_API_KEY = os.environ.get("RERANKER_API_KEY") or LLM_API_KEY
RERANKER_BASE_URL = os.environ.get("RERANKER_BASE_URL") or LLM_BASE_URL
RERANKER_MODEL = os.environ.get("RERANKER_MODEL") or "BAAI/bge-reranker-v2-m3"

if not NEO4J_URI or not NEO4J_USER or not NEO4J_PASSWORD:
    raise ValueError("NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set")

if not LLM_API_KEY:
    raise ValueError("LLM_API_KEY must be set and cannot be empty")


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


class Person(BaseModel):
    id_number: Optional[str] = Field(
        None,
        description="唯一标识ID（如 P014），用于与同名实体区分;身份证号、护照号等证件信息（建议脱敏存储）",
    )
    full_name: Optional[str] = Field(
        None, description="人物姓名，仅填写姓名本身，不包含编号"
    )
    alias: Optional[List[str]] = Field(
        None, description="人物别名、昵称、英文名或曾用名"
    )
    gender: Optional[str] = Field(None, description="性别")
    nationality: Optional[str] = Field(None, description="国籍或所属国家/地区")
    birth_date: Optional[str] = Field(None, description="出生日期")
    age: Optional[int] = Field(None, description="年龄")
    occupation: Optional[str] = Field(None, description="职业或岗位")
    affiliated_organization: Optional[str] = Field(
        None, description="所属组织、单位或机构"
    )
    phone: Optional[str] = Field(None, description="联系电话")
    email: Optional[str] = Field(None, description="电子邮箱")
    address: Optional[str] = Field(None, description="居住地址或工作地址")

    social_identity: Optional[str] = Field(
        None, description="社会身份，例如专家、记者、群众、员工、负责人等"
    )
    role: Optional[str] = Field(
        None,
        description="在当前事件中的角色，例如目击者、受害者、责任人、救援人员、调查人员等",
    )
    impact: Optional[str] = Field(
        None, description="该人物在事件中的影响、伤亡情况或作用描述"
    )
    involvement_level: Optional[str] = Field(
        None, description="参与事件的程度，例如核心相关、间接关联、旁观者等"
    )


class Organization(BaseModel):
    org_name: Optional[str] = Field(None, description="组织全称")
    country: Optional[str] = Field(None, description="所属国家或地区")
    role: Optional[str] = Field(None, description="在本事件中的角色")
    id_number: Optional[str] = Field(
        None, description="组织特征ID（唯一标识符），用于唯一标识一个组织实体"
    )
    org_alias: Optional[List[str]] = Field(None, description="组织别名、简称或历史名称")
    org_type: Optional[str] = Field(
        None,
        description="组织类型，例如政府机构、企业、媒体、学校、国际组织、科研机构、NGO等",
    )
    parent_org: Optional[str] = Field(None, description="上级组织或母公司名称")
    industry: Optional[str] = Field(
        None, description="所属行业或领域，例如化工、能源、金融、互联网、医疗等"
    )
    city: Optional[str] = Field(None, description="所在城市")
    address: Optional[str] = Field(None, description="组织地址或办公地点")
    founded_time: Optional[str] = Field(None, description="组织成立时间")
    legal_representative: Optional[str] = Field(
        None, description="法人代表、负责人或主要管理者"
    )
    impact: Optional[str] = Field(
        None, description="该组织在事件中的影响、损失或作用描述"
    )
    involvement_level: Optional[str] = Field(
        None, description="组织参与事件的程度，例如直接参与、间接关联、核心参与等"
    )
    contact_info: Optional[str] = Field(
        None, description="联系电话、邮箱或其他联系方式"
    )
    official_website: Optional[str] = Field(None, description="官方网站链接")
    description: Optional[str] = Field(None, description="组织简介或背景信息")


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


async def init_graph_client(config: dict | None = None) -> Graphiti:
    config = config or {}
    neo4j_config = config.get("neo4j", {})
    llm_config = config.get("llm", {})
    embedder_config = config.get("embedder", {})
    reranker_config = config.get("reranker", {})

    neo4j_uri = neo4j_config.get("uri", NEO4J_URI)
    neo4j_user = neo4j_config.get("user", NEO4J_USER)
    neo4j_password = neo4j_config.get("password", NEO4J_PASSWORD)

    llm_api_key = llm_config.get("api_key") or LLM_API_KEY
    llm_base_url = llm_config.get("base_url") or LLM_BASE_URL
    llm_model = llm_config.get("model") or LLM_MODEL

    embedder_api_key = embedder_config.get("api_key") or EMBEDDER_API_KEY
    embedder_api_base = embedder_config.get("api_base") or EMBEDDER_API_BASE
    embedder_model = embedder_config.get("model") or EMBEDDER_MODEL

    reranker_api_key = reranker_config.get("api_key") or RERANKER_API_KEY
    reranker_base_url = reranker_config.get("base_url") or RERANKER_BASE_URL
    reranker_model = reranker_config.get("model") or RERANKER_MODEL

    llm_client = OpenAIGenericClient(
        config=LLMConfig(
            api_key=llm_api_key,
            model=llm_model,
            base_url=llm_base_url,
        )
    )

    embedder = OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            embedding_model=embedder_model,
            api_key=embedder_api_key,
            base_url=embedder_api_base,
        )
    )

    cross_encoder = JinaRerankerClient(
        config=LLMConfig(
            api_key=reranker_api_key,
            model=reranker_model,
            base_url=reranker_base_url,
        )
    )

    graphiti = Graphiti(
        neo4j_uri,
        neo4j_user,
        neo4j_password,
        llm_client=llm_client,
        embedder=embedder,
        cross_encoder=cross_encoder,
        graph_driver=Neo4jDriver(
            neo4j_uri,
            neo4j_user,
            neo4j_password,
            database="neo4j",
        ),
    )

    await graphiti.build_indices_and_constraints()
    return graphiti


async def _safe_close_client(client: Any) -> None:
    if client is None:
        return

    close_fn = getattr(client, "aclose", None) or getattr(client, "close", None)
    if close_fn is None:
        return

    result = close_fn()
    if hasattr(result, "__await__"):
        await result


async def _close_inner_http_client(client: Any) -> None:
    """Close the inner AsyncOpenAI or httpx client if present."""
    if client is None:
        return
    for attr in ("client", "_client"):
        inner = getattr(client, attr, None)
        if inner is None:
            continue
        if callable(getattr(inner, "is_closed", None)) and inner.is_closed():
            continue
        close_fn = getattr(inner, "aclose", None) or getattr(inner, "close", None)
        if close_fn is None:
            continue
        result = close_fn()
        if hasattr(result, "__await__"):
            await result


async def close_graph_client(graphiti: Graphiti) -> None:
    for client in (
        getattr(graphiti, "llm_client", None),
        getattr(graphiti, "embedder", None),
        getattr(graphiti, "cross_encoder", None),
    ):
        try:
            await _safe_close_client(client)
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise
        try:
            await _close_inner_http_client(client)
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise

    try:
        await graphiti.close()
    except RuntimeError as e:
        if "Event loop is closed" in str(e):
            return
        raise


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
    group_id: str | None = None,
    custom_extraction_instructions: str | None = None,
    update_communities: bool = False,
    summarize_before_extract: bool = False,
    dry_run: bool = False,
) -> Any:
    effective_reference_time = reference_time or datetime.now()
    effective_source = source_description
    entity_types = {
        "Person": Person,
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
        ("Event", "Person"): ["Involves"],
        ("Person", "Organization"): ["Involves"],
        ("Event", "Commodity"): ["Involves"],
        ("Event", "Technology"): ["Involves"],
        ("Event", "Policy"): ["Involves"],
        ("Organization", "Technology"): ["Involves"],
        ("Policy", "Organization"): ["Involves"],
        ("Commodity", "Organization"): ["Involves"],
        ("Entity", "Entity"): ["Involves"],
    }
    default_custom_instructions = (
        "请优先基于输入抽取清晰、规范的事件节点，事件名必须尽量是“主体+动作/结果”的形式。"
        "如果人物/组织带有显式编号（如 P014#、C009#，或 ID: P017），必须将编号写入对应实体的id_number属性字段；即便姓名相同，id_number不同也不得合并。"
        "对于【编号# 名称】格式，必须把方括号内实体逐一抽取出来，不得漏抽。"
        "示例1：输入‘【P014# 张女士】发现机构闭店’，抽取 Person: {name: 张女士, id_number: P014}。"
        "示例2：输入‘【P017# 张女士】在超市购买熟食’，抽取 Person: {name: 张女士, id_number: P017}，与 P014实体不合并。"
        "示例3：输入‘【C009# 启航少儿艺术中心】闭店’，抽取 Organization: {name: 启航少儿艺术中心, id_number: C009}。"
        "示例4：输入‘【P015# 校区负责人李某】’，抽取 Person: {name: 李某, id_number: P015}。"
        "人物实体的name只写姓名本身，不要包含编号，也不要包含“ID:”。组织实体的name只写组织名称本身，不要包含编号。"
        "只抽取文本中明确出现的实体与关系，不要做跨段推断或补全未出现的人物。"
        "只有在事件节点已明确抽出后，才抽取因果边 Causes。"
        "如果一段输入里隐含多个事件，请拆成多个事件节点再建立因果链。"
        "自定义关系抽取逻辑保持不变，仍然优先抽取事件间因果与参与关系。"
    )
    effective_event_text = event_text
    summary_text = None

    if summarize_before_extract:
        summary_text = await _summarize_for_extraction(
            graphiti, event_text, effective_source
        )
        effective_event_text = summary_text

    _original_process: Any = None
    if dry_run:
        _original_process = graphiti._process_episode_data

        async def _noop_process(
            episode: Any,
            nodes: Any,
            entity_edges: Any,
            now: Any,
            group_id: Any,
            saga: Any = None,
            saga_previous_episode_uuid: Any = None,
            node_episode_index_map: Any = None,
        ) -> tuple[list, Any]:
            episodes = episode if isinstance(episode, list) else [episode]
            for ep in episodes:
                ep.entity_edges = [e.uuid for e in entity_edges]
            return [], episodes[0]

        graphiti._process_episode_data = _noop_process

    try:
        result = await graphiti.add_episode(
            name=effective_source,
            episode_body=effective_event_text,
            source_description=effective_source,
            reference_time=effective_reference_time,
            entity_types=entity_types,
            edge_types=edge_types,
            edge_type_map=edge_type_map,
            custom_extraction_instructions=custom_extraction_instructions
            or default_custom_instructions,
            group_id=group_id,
            update_communities=update_communities,
        )
    finally:
        if dry_run and _original_process is not None:
            graphiti._process_episode_data = _original_process

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
        "group_id": group_id,
    }


async def hybrid_search(
    graphiti: Graphiti,
    query: str,
    group_id: str | None = None,
    recipe: Any = COMBINED_HYBRID_SEARCH_CROSS_ENCODER,  # 默认
    filters: Any | None = None,
    num_results: int = 10,
    candidate_limit: int | None = None,  # 候选集数量 默认按 num_results * 2（至少 10）
    min_score: float = 0.0,  # 相关性阈值，低于此分数的结果将被丢弃
) -> Any:
    group_ids = [group_id] if group_id else None
    search_config = recipe
    if candidate_limit is None:
        candidate_limit = max(num_results * 2, 10) if num_results else 10
    if hasattr(recipe, "model_copy"):
        search_config = recipe.model_copy(update={"limit": candidate_limit})
    elif hasattr(recipe, "copy"):
        search_config = recipe.copy(update={"limit": candidate_limit})
    elif isinstance(recipe, dict):
        search_config = {**recipe, "limit": candidate_limit}

    # Graphiti 底层部分搜索实现会假定 search_filter 一定是 SearchFilters 实例。
    # 显式传空过滤器，避免 None 传入后在驱动层触发 `'NoneType' object has no attribute 'get'`。
    search_filters = filters if filters is not None else SearchFilters()

    result = await graphiti.search_(
        query,
        config=search_config,
        group_ids=group_ids,
        search_filter=search_filters,
    )
    global_ranked = None
    if num_results is not None:
        global_ranked = await _global_merge_rerank_top_k(
            graphiti=graphiti,
            query=query,
            edges=result.edges,
            nodes=result.nodes,
            episodes=result.episodes,
            communities=result.communities,
            top_k=num_results,
        )

    if min_score > 0.0 and global_ranked:
        before = len(global_ranked)
        global_ranked = [
            item
            for item in global_ranked
            if (item.get("score") if item.get("score") is not None else 0) >= min_score
        ]
        after = len(global_ranked)
        if after < before:
            logger.info(
                "相关性过滤: %d -> %d (min_score=%.2f)", before, after, min_score
            )

    return {
        "query": query,
        "results": global_ranked,
        "num_results_count": len(global_ranked) if global_ranked else 0,
        "num_results_limit": num_results,
        "group_id": group_id,
        "nodes": result.nodes,
        "edges": result.edges,
        "episodes": result.episodes,
        "communities": result.communities,
    }


async def _global_merge_rerank_top_k(
    graphiti: Graphiti,
    query: str,
    edges: list[Any],
    nodes: list[Any],
    episodes: list[Any],
    communities: list[Any],
    top_k: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, str]] = []
    for edge in edges:
        if getattr(edge, "fact", None):
            candidates.append({"type": "edge", "text": edge.fact})
    for episode in episodes:
        if getattr(episode, "content", None):
            candidates.append({"type": "episode", "text": episode.content})

    if not candidates or top_k <= 0:
        return []

    text_to_type: dict[str, str] = {}
    unique_texts: list[str] = []
    for item in candidates:
        text = item["text"]
        if text not in text_to_type:
            text_to_type[text] = item["type"]
            unique_texts.append(text)

    reranked = await graphiti.cross_encoder.rank(query, unique_texts)
    top_ranked: list[dict[str, Any]] = []
    for text, score in reranked:
        if len(top_ranked) >= top_k:
            break
        top_ranked.append(
            {
                "type": text_to_type.get(text, "unknown"),
                "text": text,
                "score": score,
            }
        )

    return top_ranked


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


async def batch_add_to_graph(
    graphiti: Graphiti,
    events: list[dict],
    group_id: str,
    dry_run: bool = False,
) -> list[dict]:
    """
    批量将多个事件写入图谱。

    Args:
        graphiti: Graphiti 客户端实例
        events: 事件列表，每个元素包含 {"text": ..., "reference_time": ..., ...}
        group_id: 事件分组 ID
        dry_run: 是否跳过 Neo4j 写入

    Returns:
        list[dict]: 每个事件的写入结果（与 add_event_to_graph 返回值格式一致）
    """
    results = []
    for event in events:
        event_text = event.get("text", "")
        reference_time = event.get("reference_time")
        if isinstance(reference_time, str):
            try:
                reference_time = datetime.fromisoformat(reference_time)
            except ValueError:
                reference_time = datetime.now()
        elif reference_time is None:
            reference_time = datetime.now()

        try:
            result = await add_event_to_graph(
                graphiti=graphiti,
                event_text=event_text,
                reference_time=reference_time,
                source_description=f"batch:{group_id}",
                group_id=group_id,
                dry_run=dry_run,
            )
            results.append(result)
        except Exception as e:
            logger.error("batch_add_to_graph failed for event: %s", e)
            results.append(
                {
                    "success": False,
                    "error": str(e),
                    "entities_extracted": 0,
                    "relations_created": 0,
                }
            )

    total_nodes = sum(r.get("entities_extracted", 0) for r in results)
    total_edges = sum(r.get("relations_created", 0) for r in results)
    logger.info(
        "batch_add_to_graph complete: %d events, %d nodes, %d edges",
        len(results),
        total_nodes,
        total_edges,
    )
    return results
