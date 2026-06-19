import logging
import os
from datetime import datetime
from typing import Any, Optional

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
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD") or "pa55w0rd"
_BASE_LLM_API_KEY = os.environ.get("LLM_API_KEY")
_BASE_LLM_BASE_URL = os.environ.get("LLM_BASE_URL") or "https://api.openai.com/v1"
_BASE_LLM_MODEL = os.environ.get("LLM_MODEL") or "gpt-4o"


def _get_llm_extract_env(name: str, fallback: str | None) -> str | None:
    """读取 Graphiti 抽取档 LLM 环境变量，未设置时回退到基础 LLM_*。"""
    return os.environ.get(f"LLM_EXTRACT_{name}") or fallback


LLM_API_KEY = _get_llm_extract_env("API_KEY", _BASE_LLM_API_KEY)
LLM_BASE_URL = _get_llm_extract_env("BASE_URL", _BASE_LLM_BASE_URL)
LLM_MODEL = _get_llm_extract_env("MODEL", _BASE_LLM_MODEL)

EMBEDDER_API_KEY = os.environ.get("EMBEDDER_API_KEY") or _BASE_LLM_API_KEY
EMBEDDER_API_BASE = os.environ.get("EMBEDDER_API_BASE") or _BASE_LLM_BASE_URL
EMBEDDER_MODEL = os.environ.get("EMBEDDER_MODEL") or "BAAI/bge-m3"

RERANKER_API_KEY = os.environ.get("RERANKER_API_KEY") or _BASE_LLM_API_KEY
RERANKER_BASE_URL = os.environ.get("RERANKER_BASE_URL") or _BASE_LLM_BASE_URL
RERANKER_MODEL = os.environ.get("RERANKER_MODEL") or "BAAI/bge-reranker-v2-m3"


def _resolve_graphiti_llm_config(
    llm_config: dict[str, Any] | None = None,
) -> dict[str, str | None]:
    """解析 Graphiti 内部抽取 LLM 配置。

    `main.load_config()` 会携带基础 `LLM_*` 配置传入 Graphiti。这里让
    `LLM_EXTRACT_*` 优先于传入 config，确保 Graphiti 抽取走 extract 档。
    """
    llm_config = llm_config or {}
    return {
        "api_key": os.environ.get("LLM_EXTRACT_API_KEY")
        or llm_config.get("api_key")
        or LLM_API_KEY,
        "base_url": os.environ.get("LLM_EXTRACT_BASE_URL")
        or llm_config.get("base_url")
        or LLM_BASE_URL,
        "model": os.environ.get("LLM_EXTRACT_MODEL")
        or llm_config.get("model")
        or LLM_MODEL,
    }


# Credential validation deferred to init_graph_client() — keeps module import-safe.


# ========================
# Pydantic schema models
# ========================


class RiskEvent(BaseModel):
    """银行零售风控/反欺诈/反洗钱事件。"""

    event_category: Optional[str] = Field(
        None,
        description="事件类别，如 normal_transaction、fraud_transfer、aml_structuring、loan_fraud、device_geo_anomaly、complaint。",
    )
    occurred_at: Optional[str] = Field(None, description="事件发生时间，优先保留原文时间")
    amount: Optional[float] = Field(None, description="事件涉及金额，单位为人民币元")
    currency: Optional[str] = Field(None, description="币种，默认人民币时可填 CNY")
    risk_level_hint: Optional[str] = Field(None, description="原文明确给出的风险等级或处置紧急程度")
    disposition: Optional[str] = Field(None, description="已执行或建议的处置，如拦截、冻结、复核、暂存、回访")
    evidence: Optional[str] = Field(None, description="支撑该事件的关键证据摘要")


class Customer(BaseModel):
    """银行客户、申请人、投诉人、转账发起人等自然人或个体工商户主体。"""

    id_number: Optional[str] = Field(None, description="显式编号，如 P105；来自【P105# 客户E】时必须填写 P105")
    customer_role: Optional[str] = Field(None, description="客户在事件中的角色，如付款方、收款方、投诉人、贷款申请人、疑似受害人")
    risk_profile: Optional[str] = Field(None, description="客户风险画像，如黑名单命中、常驻城市、历史交易稳定、涉诈受害风险")
    usual_city: Optional[str] = Field(None, description="客户常驻城市或常用地点")
    account_age_hint: Optional[str] = Field(None, description="客户或其相关账户开户时长描述")


class Account(BaseModel):
    """银行账户、收款账户、新开户账户、涉诈账户、外部支付账户等资金载体。"""

    id_number: Optional[str] = Field(None, description="显式编号，如 P305、A001；来自【编号# 名称】时必须填写")
    account_role: Optional[str] = Field(None, description="账户角色，如付款账户、收款账户、涉诈账户、跑分账户、归集账户、出金账户")
    account_status: Optional[str] = Field(None, description="账户状态，如新开户、冻结、黑名单、可疑、正常")
    opened_duration: Optional[str] = Field(None, description="开户时长，如不足7天、不足24小时")
    owner_hint: Optional[str] = Field(None, description="原文明确给出的账户归属主体")


class Merchant(BaseModel):
    """企业、商户、平台、支付通道、雇主、银行系统等非个人主体。"""

    id_number: Optional[str] = Field(None, description="显式编号，如 C301；来自【编号# 名称】时必须填写")
    merchant_type: Optional[str] = Field(None, description="主体类型，如雇主企业、超市、虚拟币平台、投资平台、外部支付通道、反洗钱系统")
    risk_status: Optional[str] = Field(None, description="商户风险状态，如涉诈、高投诉、正常、反洗钱关注")


class Device(BaseModel):
    """登录或交易设备、IP、验证码、设备指纹等端侧行为载体。"""

    device_type: Optional[str] = Field(None, description="设备类型，如常用手机、新设备、境外IP、设备指纹")
    device_status: Optional[str] = Field(None, description="设备状态，如首次登录、常用设备、异常设备")
    login_city: Optional[str] = Field(None, description="登录城市或 IP 所在地")
    auth_signal: Optional[str] = Field(None, description="认证信号，如短信验证码多次失败、回访无人接听")


class RiskSignal(BaseModel):
    """可解释风险信号、规则命中、风险关键词或模型线索。"""

    signal_type: Optional[str] = Field(None, description="信号类型，如 blacklist_hit、fraud_keyword、aml_rule、device_geo、velocity、complaint_similarity")
    severity: Optional[str] = Field(None, description="风险严重度，如 low、medium、high")
    rule_id: Optional[str] = Field(None, description="规则或案例编号，如 E-FIN-AML-001")
    evidence: Optional[str] = Field(None, description="命中证据或触发原因")


class TransfersFunds(BaseModel):
    """资金从一个客户、账户或商户流向另一个客户、账户或商户。入账、出金、归集都用此关系表达。"""

    amount: Optional[float] = Field(None, description="金额，单位人民币元")
    transaction_time: Optional[str] = Field(None, description="交易发生时间")
    remark: Optional[str] = Field(None, description="交易备注")
    channel: Optional[str] = Field(None, description="交易渠道")
    flow_type: Optional[str] = Field(None, description="资金流类型，如转账、工资入账、消费、出金、归集")


class UsesDevice(BaseModel):
    """客户或交易使用某设备、IP 或认证信号。"""

    device_status: Optional[str] = Field(None, description="新设备、常用设备、境外IP、验证码失败等")
    login_city: Optional[str] = Field(None, description="登录地点")


class TriggersSignal(BaseModel):
    """事件、客户、账户、商户或交易触发某个风险信号。"""

    trigger_reason: Optional[str] = Field(None, description="触发原因")
    severity: Optional[str] = Field(None, description="风险严重度")


class MatchesPattern(BaseModel):
    """事件或交易匹配历史案例、规则、相似投诉或异常模式。"""

    pattern_name: Optional[str] = Field(None, description="匹配模式名称")
    similarity_score: Optional[float] = Field(None, description="相似度分数，如原文明确给出")


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

    graphiti_llm_config = _resolve_graphiti_llm_config(llm_config)
    llm_api_key = graphiti_llm_config["api_key"]
    llm_base_url = graphiti_llm_config["base_url"]
    llm_model = graphiti_llm_config["model"]

    embedder_api_key = embedder_config.get("api_key") or EMBEDDER_API_KEY
    embedder_api_base = embedder_config.get("api_base") or EMBEDDER_API_BASE
    embedder_model = embedder_config.get("model") or EMBEDDER_MODEL

    reranker_api_key = reranker_config.get("api_key") or RERANKER_API_KEY
    reranker_base_url = reranker_config.get("base_url") or RERANKER_BASE_URL
    reranker_model = reranker_config.get("model") or RERANKER_MODEL

    # ------- runtime credential validation ------ 
    if not neo4j_uri or not neo4j_user or not neo4j_password:
        raise ValueError("NEO4J_URI, NEO4J_USER, and NEO4J_PASSWORD must be set")
    if not llm_api_key:
        raise ValueError(
            "Graphiti LLM api_key must be set via LLM_EXTRACT_API_KEY, "
            "config['llm']['api_key'], or LLM_API_KEY"
        )
    # ---------------------------------------------

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
        "Customer": Customer,
        "Account": Account,
        "Merchant": Merchant,
        "Device": Device,
        "RiskSignal": RiskSignal,
        "RiskEvent": RiskEvent,
    }

    edge_types = {
        "TransfersFunds": TransfersFunds,
        "UsesDevice": UsesDevice,
        "TriggersSignal": TriggersSignal,
        "MatchesPattern": MatchesPattern,
    }

    edge_type_map = {
        ("Customer", "Account"): ["TransfersFunds"],
        ("Customer", "Merchant"): ["TransfersFunds"],
        ("Customer", "Device"): ["UsesDevice"],
        ("Customer", "RiskSignal"): ["TriggersSignal"],
        ("Customer", "RiskEvent"): ["TriggersSignal", "MatchesPattern"],
        ("Account", "Customer"): ["TransfersFunds"],
        ("Account", "Account"): ["TransfersFunds"],
        ("Account", "Merchant"): ["TransfersFunds"],
        ("Account", "RiskSignal"): ["TriggersSignal"],
        ("Merchant", "Account"): ["TransfersFunds"],
        ("Merchant", "RiskSignal"): ["TriggersSignal", "MatchesPattern"],
        ("Device", "RiskSignal"): ["TriggersSignal"],
        ("RiskEvent", "Customer"): ["TriggersSignal", "MatchesPattern"],
        ("RiskEvent", "Account"): ["TransfersFunds", "TriggersSignal"],
        ("RiskEvent", "Merchant"): ["TransfersFunds", "TriggersSignal", "MatchesPattern"],
        ("RiskEvent", "Device"): ["UsesDevice"],
        ("RiskEvent", "RiskSignal"): ["TriggersSignal", "MatchesPattern"],
        ("Entity", "Entity"): list(edge_types.keys()),
    }
    default_custom_instructions = """
你正在为“端侧银行零售反欺诈与反洗钱预警助手”快速构建轻量知识图谱。
目标是保留风控研判需要的最小事实：主体、资金流、设备异常、风险信号、相似模式。

实体抽取规则：
1. 对所有【编号# 名称】必须逐一抽取，name 严格等于“名称”，id_number 严格等于“编号”。
   例如【P105# 客户E】 -> name=客户E, id_number=P105；
   不要输出“客户”“账户”这种短泛称替代完整名称；不要把编号写进 name。
2. 实体分类按语义和上下文，不要只看编号前缀：
   - 客户A、客户E、个体工商户F、投诉人、贷款申请人 -> Customer
   - 涉诈账户、新收款账户、付款账户、收款账户、跑分账户、归集账户 -> Account
   - 虚拟币平台、投资平台、外部支付通道、超市、雇主企业、反洗钱系统 -> Merchant
   - 新设备、常用手机、境外IP、短信验证码、登录设备 -> Device
   - 洗钱、分拆交易、涉诈、黑名单、虚拟币保证金、投诉相似、开户不足7天、验证码失败 -> RiskSignal
   - 转账、入账、消费、出金、贷款申请、投诉、冻结复核等完整事件 -> RiskEvent
3. 不要抽取单独的时间、地点、金额、交易备注、投诉话术为实体；这些信息写进属性或关系 fact。
4. 只抽取原文明确出现或无歧义蕴含的实体，不要补全未出现的信息。

关系抽取规则：
1. 资金入账、转账、消费、归集、出金都统一使用 TransfersFunds，不再使用接收/归集等拆分关系。
2. 设备/IP/验证码/异地登录统一用 UsesDevice。
3. 黑名单、涉诈、洗钱、分拆、开户过短、贷款欺诈、投诉相似等风险命中统一用 TriggersSignal。
4. 历史相似事件、相似投诉话术、相似规则案例统一用 MatchesPattern。
5. 每条关系的 fact 用中文，保留金额、时间、备注、渠道、设备状态、开户时长、处置建议等关键证据，不要泛化：
   好：客户E在2026年6月13日10:24尝试向涉诈账户转账98000元，备注为虚拟币保证金。
   坏：客户进行了可疑交易。
6. 为速度考虑，不要抽取低价值泛关系；每个事件优先保留 3-6 条最关键关系即可。
"""
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
