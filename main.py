"""
Sentinel 舆情分析系统 — Phase 1 主入口（模拟运行）
=====================================================
串联 Ingestion → Classification → Graph → Dashboard。

调用方式:
  python main.py
"""

import argparse
import asyncio
import json
import os
import random
import re
import logging
import time
import traceback
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
from models import (
    NormalizedEvent,
    EventSource,
    to_queue_message,
)
from consumer import (
    normalize_event,
    is_duplicate,
    reset_duplicate_cache,
)
from crewai.flow.flow import Flow, listen, start, router
from crewai import Agent, Task, Crew, Process
from log_utils import (
    print_info,
    print_warn,
    print_error,
    print_banner,
    get_logger,
    setup_file_logging,
)
from providers.llm_provider import close_all_llms


# ============================================================
#  全局配置加载
# ============================================================


def load_config() -> dict:
    """
    加载并合并配置，优先级: 环境变量 > .env 文件 > 默认值

    Returns:
        dict: 合并后的配置字典
    """
    config = {
        "rabbitmq": {
            "host": os.getenv("RABBITMQ_HOST") or "localhost",
            "port": int(os.getenv("RABBITMQ_PORT") or "5672"),
            "user": os.getenv("RABBITMQ_USER") or "guest",
            "password": os.getenv("RABBITMQ_PASSWORD") or "password",
        },
        "neo4j": {
            "uri": os.getenv("NEO4J_URI") or "bolt://localhost:7687",
            "user": os.getenv("NEO4J_USER") or "neo4j",
            "password": os.getenv("NEO4J_PASSWORD") or "password",
        },
        "llm": {
            "api_key": os.getenv("LLM_API_KEY") or "",
            "base_url": os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1",
            "model": os.getenv("LLM_MODEL") or "gpt-4o",
        },
        "embedder": {
            "model": os.getenv("EMBEDDER_MODEL") or "BAAI/bge-m3",
            "api_key": os.getenv("EMBEDDER_API_KEY") or os.getenv("LLM_API_KEY") or "",
            "api_base": os.getenv("EMBEDDER_API_BASE") or "https://api.openai.com/v1",
        },
        "graphiti": {
            "episode_source_name": os.getenv("GRAPHITI_EPISODE_SOURCE") or "sentinel",
        },
        "search": {
            "num_results": int(os.getenv("SEARCH_NUM_RESULTS") or "10"),
            "risk_num_results": int(
                os.getenv("RISK_SEARCH_NUM_RESULTS")
                or os.getenv("SEARCH_NUM_RESULTS")
                or "20"
            ),
            "min_score": float(os.getenv("SEARCH_MIN_SCORE") or "0.0"),
        },
        "classification": {
            "risk_threshold": float(os.getenv("RISK_THRESHOLD") or "0.2"),
        },
    }
    logger = get_logger("main.config")
    logger.info(
        "config loaded: rabbitmq=%s:%s, neo4j=%s, llm=%s, embedder=%s",
        config["rabbitmq"]["host"],
        config["rabbitmq"]["port"],
        config["neo4j"]["uri"],
        config["llm"]["model"],
        config["embedder"]["model"],
    )
    return config


# ============================================================
#  模拟数据工厂
# ============================================================

# 模拟的原始事件池
MOCK_RAW_EVENTS = [
    {
        "source": "news",
        "content": "某科技公司因产品质量问题被监管部门立案调查，股价暴跌15%",
        "title": "科技巨头遭调查",
    },
    {
        "source": "news",
        "content": "国务院发布新一轮数字经济扶持政策，重点支持人工智能和量子计算领域",
        "title": "数字经济新政策",
    },
    {
        "source": "chat",
        "content": "用户A: 这个App更新后闪退严重\n用户B: 我也是，客服说在修了\n用户C: 已经三天了还没修好",
        "title": "App闪退投诉",
    },
    {
        "source": "news",
        "content": "某知名企业家在公开场合发表不当言论，引发社交媒体热议和品牌抵制",
        "title": "企业家不当言论",
    },
    {
        "source": "transaction",
        "content": "账户T001向账户T002转账500万元，触发大额交易预警",
        "title": "大额转账预警",
    },
    {
        "source": "behavior",
        "content": "用户U123在24小时内访问了12个竞争对手网站并下载3份报价单",
        "title": "异常访问行为",
    },
    {
        "source": "news",
        "content": "某新能源企业电池工厂发生火灾事故，附近居民紧急疏散",
        "title": "电池工厂火灾",
    },
    {
        "source": "chat",
        "content": "员工E001: 公司下个月可能裁员30%\n员工E002: 哪来的消息？\n员工E001: HR部门的朋友说的",
        "title": "裁员传闻",
    },
    {
        "source": "news",
        "content": "央行宣布下调存款准备金率0.5个百分点，释放长期流动性约1万亿元",
        "title": "央行降准",
    },
    {
        "source": "transaction",
        "content": "账户T003连续7天在同一商户消费，每日金额递增，疑似洗钱行为",
        "title": "可疑交易模式",
    },
]

# 模拟原始事件（结构化格式，对应不同 source 的特有字段）
MOCK_RAW_EVENTS_STRUCTURED = [
    {  # 新闻 结构化
        "source": "news",
        "content": "某科技公司因产品质量问题被监管部门立案调查，股价暴跌15%",
        "title": "科技巨头遭调查",
        "author": "财经日报",
        "url": "https://news.example.com/tech-investigation",
        "source_name": "财经日报",
        "timestamp": datetime.now() - timedelta(hours=2),
    },
    {  # 聊天 结构化
        "source": "chat",
        "content": "用户A: 这个App更新后闪退严重\n用户B: 我也是",
        "title": "App闪退投诉",
        "platform": "WeChat",
        "participants": ["用户A", "用户B", "用户C"],
        "channel_id": "group_12345",
        "timestamp": datetime.now() - timedelta(hours=1),
    },
    {  # 交易 结构化
        "source": "transaction",
        "content": "账户T001向账户T002转账500万元，触发大额交易预警",
        "title": "大额转账预警",
        "from_account": "T001",
        "to_account": "T002",
        "amount": 5000000,
        "currency": "CNY",
        "timestamp": datetime.now() - timedelta(minutes=30),
    },
    {  # 行为 结构化
        "source": "behavior",
        "content": "用户U123在24小时内访问了12个竞争对手网站并下载3份报价单",
        "title": "异常访问行为",
        "user_id": "U123",
        "action": "page_visit",
        "target": "competitor.com",
        "device": "Windows 11",
        "timestamp": datetime.now() - timedelta(minutes=10),
    },
]


def generate_mock_raw_event() -> dict:
    """从事件池随机抽取一条原始事件（结构化格式）"""
    return random.choice(MOCK_RAW_EVENTS_STRUCTURED).copy()


# ============================================================
#  Stage 1: Ingestion — 事件接入与标准化
# ============================================================


def simulate_ingestion(config: dict, event_count: int = 5) -> list:
    """
    模拟事件接入服务：多源消费 + 标准化 + 去重 + 转发
    调用真实的 normalize_event() 和 is_duplicate() 函数。

    Args:
        config: 全局配置
        event_count: 模拟处理的事件数量

    Returns:
        list[NormalizedEvent]: 标准化后的 NormalizedEvent 对象列表
    """
    logger = get_logger("main.ingestion")

    reset_duplicate_cache()
    normalized_events = []

    for i in range(event_count):
        raw = generate_mock_raw_event()
        source = raw["source"]

        print_info(f"消费 raw event #{i + 1} (source={source})")
        logger.info(
            "raw event #%d: title=%s, content=%.50s",
            i + 1,
            raw["title"],
            raw["content"],
        )

        normalized = normalize_event(raw, source)

        if is_duplicate(normalized.event_id):
            print_info(f"事件重复，跳过: {normalized.event_id}")
            logger.info("duplicate event skipped: %s", normalized.event_id)
            continue

        logger.info(
            "normalized: event_id=%s, trace_id=%s, source=%s, content_type=%s, structured_keys=%s",
            normalized.event_id,
            normalized.trace_id,
            normalized.source.value,
            normalized.content_type,
            list(normalized.structured_data.keys()),
        )

        normalized_events.append(normalized)

        message = to_queue_message(normalized, "normalized", normalized.trace_id)
        logger.info(
            "published to sentinel.internal.normalized, size=%d bytes",
            len(json.dumps(message, ensure_ascii=False)),
        )

    print_info(
        f"完成: 共处理 {len(normalized_events)} 条事件, "
        f"去重跳过 {event_count - len(normalized_events)} 条"
    )
    return normalized_events


# ============================================================
#  Stage 2: Classification — CrewAI 分类评级
# ============================================================


def classify_event(config: dict, normalized_event: dict) -> dict:
    logger = get_logger("main.classification")
    from providers.llm_provider import get_llm

    llm = get_llm(
        model=config["llm"]["model"],
        api_key=config["llm"]["api_key"],
        base_url=config["llm"]["base_url"],
        temperature=0.3,
    )

    type_classifier = Agent(
        llm=llm,
        role="事件类型分类专家",
        goal="从文本内容中准确识别事件类型并提取关键实体",
        backstory="你是一位资深的舆情分析师，擅长从各种文本中识别事件类型并提取关键实体。",
        verbose=True,
    )

    classify_task = Task(
        name="事件分类",
        description="分析以下事件内容，识别事件类型并提取关键实体(人物、组织、地点)，不提取中性物品、无关人物、主观情绪、背景常识。"
        "事件内容: {event_content}。 "
        "请输出 JSON 格式, 包含 event_type:str, key_entities:dict, summary:str 字段。不要markdown格式和任何解释",
        agent=type_classifier,
        expected_output="JSON 格式的分类结果",
    )

    crew = Crew(
        agents=[type_classifier],
        tasks=[classify_task],
        process=Process.sequential,
        verbose=True,
    )

    if isinstance(normalized_event, NormalizedEvent):
        raw_content = normalized_event.raw_content
        title = normalized_event.title
    else:
        raw_content = normalized_event.get("raw_content", "")
        title = normalized_event.get("title", "")

    result = crew.kickoff(
        inputs={
            "event_content": f"标题: {title}\n内容: {raw_content}",
        }
    )

    try:
        result_text = str(result.raw)
        result_dict = json.loads(result_text)

        return {
            "event_type": result_dict.get("event_type", "信息传播"),
            "key_entities": result_dict.get("key_entities", {}),
            "summary": result_dict.get("summary", ""),
        }
    except Exception as e:
        print_error("分类结果解析失败")
        logger.error("parse classification result failed: %s", e, exc_info=True)
        return None


def evaluate_risk(config: dict, event: NormalizedEvent) -> dict:
    logger = get_logger("main.risk_evaluation")
    from providers.llm_provider import get_llm

    llm = get_llm(
        model=config["llm"]["model"],
        api_key=config["llm"]["api_key"],
        base_url=config["llm"]["base_url"],
        temperature=0.1,
    )

    risk_evaluator = Agent(
        llm=llm,
        role="风险评估专家",
        goal="评估事件的风险等级和风险分数",
        backstory="你是一位风险评估专家，擅长评估事件的潜在风险。",
        verbose=True,
    )

    risk_task = Task(
        name="风险评估",
        description="基于事件信息从人物、物品、组织、地点、事件、重要时间等各角度，进行高标准的评估风险等级，不能忽略任何细微的风险。核心评估原则：物品、组织本身无善恶、不主动害人，但人可利用物品或组织实施伤人、滋事、违法、肇事等行为，只要存在被恶意利用、不当使用、违规流转的可能性，该物品及关联行为一律纳入风险研判，不做无风险默认化判定。示例逻辑参照：普通菜刀本身是生活用具无危害，但人可网购、持有、携带、改用菜刀伤人、寻衅滋事，因此网购菜刀、私下持有刀具、陌生人员购置锐器等场景必须研判潜在风险，不能仅按日常用品判定无风险。"
        "事件类型: {event_type}, 事件摘要: {summary}, 关键实体: {entities}，事件发生时间: {event_date},数据来源: {source}。"
        "请输出 JSON 格式: risk_level (high/medium/low), risk_score (0.0-1.0), reasoning",
        agent=risk_evaluator,
        output_format="json",
        expected_output="JSON 格式的风险评估结果",
    )

    crew = Crew(
        agents=[risk_evaluator],
        tasks=[risk_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff(
        inputs={
            "event_type": event.event_type,
            "summary": event.summary,
            "entities": str(event.structured_data),
            "event_date": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "source": event.source,
        }
    )

    try:
        result_dict = json.loads(result.raw)

        risk_score = result_dict.get("risk_score", 0.5)
        if isinstance(risk_score, str):
            risk_score = float(risk_score)

        return {
            "risk_level": result_dict.get("risk_level", "medium"),
            "risk_score": risk_score,
            "reasoning": result_dict.get("reasoning", ""),
        }
    except Exception as e:
        print_error("风险评估结果解析失败")
        logger.error("parse risk evaluation result failed: %s", e, exc_info=True)
        return {
            "risk_level": "medium",
            "risk_score": 0.5,
            "reasoning": "自动评估",
        }


def second_evaluate_risk(config: dict, event: NormalizedEvent, results: dict) -> dict:
    logger = get_logger("main.risk_evaluation")
    from providers.llm_provider import get_llm

    llm = get_llm(temperature=0.1)

    risk_evaluator = Agent(
        llm=llm,
        role="风险评估专家",
        goal="评估事件的风险等级和风险分数",
        backstory="你是一位风险评估专家，擅长评估事件的潜在风险。",
        verbose=True,
    )
    reranked_edges = results.get("reranked_edges", []) if results else []
    reranked_episodes = results.get("reranked_episodes", []) if results else []

    related_events_parts = []
    for item in reranked_edges:
        text = (
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        )
        if text:
            related_events_parts.append(f"[edge] {text}")
    for item in reranked_episodes:
        text = (
            item.get("text")
            if isinstance(item, dict)
            else getattr(item, "content", None)
        )
        if text:
            related_events_parts.append(f"[episode] {text}")

    related_events = "\n".join(related_events_parts)
    risk_task = Task(
        name="二次风险评估",
        description="基于事件信息从人物、组织、地点、事件、重要时间等各角度，进行风险评估。"
        "事件类型: {event_type}, 事件摘要: {summary}, 关键实体: {entities}，事件发生时间: {event_date},数据来源: {source}。"
        "关联事件信息: {related_events}"
        "请输出 JSON 格式: risk_level (high/medium/low), risk_score (0.0-1.0), reasoning",
        agent=risk_evaluator,
        output_format="json",
        expected_output="JSON 格式的风险评估结果",
    )

    crew = Crew(
        agents=[risk_evaluator],
        tasks=[risk_task],
        process=Process.sequential,
        verbose=True,
    )

    print_info("开始第二次风险评估")
    result = crew.kickoff(
        inputs={
            "event_type": event.event_type,
            "summary": event.summary,
            "entities": str(event.structured_data),
            "event_date": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "source": event.source,
            "related_events": related_events,
        }
    )

    try:
        result_dict = json.loads(result.raw)

        risk_score = result_dict.get("risk_score", 0.5)
        if isinstance(risk_score, str):
            risk_score = float(risk_score)

        final_result = {
            "risk_level": result_dict.get("risk_level", "medium"),
            "risk_score": risk_score,
            "reasoning": result_dict.get("reasoning", ""),
        }
        print_info(
            f'第二次风险评估完成: risk_level="{final_result["risk_level"]}", risk_score={final_result["risk_score"]}'
        )
        return final_result
    except Exception as e:
        print_error("风险评估结果解析失败")
        logger.error("parse second risk evaluation result failed: %s", e, exc_info=True)
        return {
            "risk_level": "medium",
            "risk_score": 0.5,
            "reasoning": "自动评估",
        }


def simulate_classification(
    config: dict, normalized_events: NormalizedEvent
) -> NormalizedEvent:
    logger = get_logger("main.classification")

    classification_result = classify_event(config, normalized_events)

    if classification_result is None:
        print_error("分类失败，使用默认值")
        return normalized_events

    event_type = classification_result["event_type"]
    key_entities = classification_result["key_entities"]
    summary = classification_result["summary"]

    logger.info(
        "classification result: event_type=%s, entities=%d",
        event_type,
        len(key_entities),
    )

    normalized_events.event_type = event_type
    normalized_events.structured_data = key_entities
    normalized_events.summary = summary

    print_info("分类完成")
    return normalized_events


# ============================================================
#  Stage 3: Graph — Graphiti 知识图谱构图
# ============================================================


async def get_graphiti_client(config: dict):
    """获取 Graphiti 客户端"""
    from graphiti.graphiti_workflow import init_graph_client

    return await init_graph_client(config)


async def simulate_graph_build(config: dict, event: NormalizedEvent) -> list:
    """
    知识图谱构建：Graphiti Episode 写入 + 实体/关系提取

    Args:
        config: 全局配置
        event: 标准化事件

    Returns:
        list[dict]: GraphBuildResult 列表
    """
    logger = get_logger("main.graph")
    from graphiti.graphiti_workflow import add_event_to_graph, close_graph_client

    graphiti = await get_graphiti_client(config)

    logger.info(
        "Graphiti client initialized: neo4j=%s, llm=%s, embedder=%s",
        config["neo4j"]["uri"],
        config["llm"]["model"],
        config["embedder"]["model"],
    )
    print_info("Graphiti 客户端初始化完成")

    build_results = []

    group_id = config.get("graphiti", {}).get("episode_source_name", "sentinel")
    logger.info("writing event_id=%s, group_id=%s", event.event_id, group_id)

    timestamp = event.timestamp

    try:
        result = await add_event_to_graph(
            graphiti=graphiti,
            event_text=event.raw_content,
            reference_time=timestamp,
            source_description=f"{event.source}:{event.event_type}",
            group_id=group_id,
        )

        entities = result.get("entities_extracted", 0)
        relations = result.get("relations_created", 0)
        print_info(f"写入成功: {entities} 个实体, {relations} 条关系")
        logger.info(
            "graph write success: entities=%d, relations=%d", entities, relations
        )

        build_results.append(
            {
                "event_id": event.event_id,
                "success": True,
                "entities_extracted": entities,
                "relations_created": relations,
            }
        )

    except Exception as e:
        print_error("图谱写入失败")
        logger.error("graph write failed: %s", e, exc_info=True)
        build_results.append(
            {
                "event_id": event.event_id,
                "success": False,
                "error": str(e),
            }
        )
    finally:
        total_nodes = sum(r.get("entities_extracted", 0) for r in build_results)
        total_edges = sum(r.get("relations_created", 0) for r in build_results)
        logger.info(
            "graph build done: %d episodes, %d nodes, %d edges",
            len(build_results),
            total_nodes,
            total_edges,
        )

        await close_graph_client(graphiti)

    return build_results


# ============================================================
#  Stage 4: Search — 混合搜索演示
# ============================================================


def extract_subject_id_numbers(text: str) -> list[str]:
    """从当前事件文本中抽取主体 id_number，例如【P01# 小明】中的 P01。

    检索范围只使用稳定 id_number，不使用人名兜底，避免同名主体误召回。
    """
    id_numbers: list[str] = []
    seen: set[str] = set()

    for entity_id in re.findall(r"【\s*([A-Za-z]+\d+)\s*#\s*[^】]+?\s*】", text):
        normalized_id = entity_id.strip().upper()
        if normalized_id and normalized_id not in seen:
            id_numbers.append(normalized_id)
            seen.add(normalized_id)

    for entity_id in re.findall(r"\b([A-Za-z]+\d+)\b", text):
        normalized_id = entity_id.strip().upper()
        if normalized_id and normalized_id not in seen:
            id_numbers.append(normalized_id)
            seen.add(normalized_id)

    return id_numbers


async def get_subject_episode_uuids(
    graphiti, id_numbers: list[str], group_id: str
) -> set[str]:
    """查找所有包含指定 id_number 主体的 Episode UUID。

    这里的“包含”指 Episode 通过 MENTIONS 关系直接提到了 id_number=P01 的实体，
    不是从 P01 出发扩展一跳/多跳邻居子图。
    """
    if not id_numbers:
        return set()

    records, _, _ = await graphiti.driver.execute_query(
        """
        MATCH (e:Episodic)-[:MENTIONS]->(n:Entity)
        WHERE e.group_id = $group_id
          AND toUpper(toString(n.id_number)) IN $id_numbers
        RETURN DISTINCT e.uuid AS uuid
        """,
        group_id=group_id,
        id_numbers=[id_number.upper() for id_number in id_numbers],
        routing_="r",
    )
    return {record["uuid"] for record in records if record.get("uuid")}


def filter_search_result_by_subject_episodes(
    result: dict, episode_uuids: set[str], id_numbers: list[str]
) -> dict:
    """只保留“包含当前主体 id_number 的 Episode”及其内部结果。"""
    if not id_numbers or not result:
        return result

    if not episode_uuids:
        scoped_result = dict(result)
        scoped_result["scope_mode"] = "subject_episode"
        scoped_result["subject_id_numbers"] = id_numbers
        scoped_result["subject_episode_uuids"] = []
        scoped_result["edges"] = []
        scoped_result["nodes"] = []
        scoped_result["episodes"] = []
        scoped_result["results"] = []
        scoped_result["num_results_count"] = 0
        return scoped_result

    scoped_episodes = [
        episode
        for episode in result.get("episodes", [])
        if getattr(episode, "uuid", None) in episode_uuids
    ]
    scoped_edge_uuids = {
        edge_uuid
        for episode in scoped_episodes
        for edge_uuid in getattr(episode, "entity_edges", [])
    }
    scoped_edges = [
        edge
        for edge in result.get("edges", [])
        if getattr(edge, "uuid", None) in scoped_edge_uuids
    ]
    scoped_node_uuids = {
        node_uuid
        for edge in scoped_edges
        for node_uuid in (
            getattr(edge, "source_node_uuid", None),
            getattr(edge, "target_node_uuid", None),
        )
        if node_uuid
    }
    scoped_nodes = [
        node
        for node in result.get("nodes", [])
        if getattr(node, "uuid", None) in scoped_node_uuids
    ]

    scoped_texts: list[str] = []
    for episode in scoped_episodes:
        content = getattr(episode, "content", None)
        if content:
            scoped_texts.append(str(content))
    for edge in scoped_edges:
        fact = getattr(edge, "fact", None)
        if fact:
            scoped_texts.append(str(fact))

    filtered_results = []
    for item in result.get("results", []):
        text = item.get("text", "")
        if any(text and text in scoped_text for scoped_text in scoped_texts):
            filtered_results.append(item)

    if not filtered_results:
        filtered_results = [
            {"type": "subject_episode", "text": text, "score": None}
            for text in scoped_texts[: result.get("num_results_limit", 10)]
        ]

    scoped_result = dict(result)
    scoped_result["scope_mode"] = "subject_episode"
    scoped_result["subject_id_numbers"] = id_numbers
    scoped_result["subject_episode_uuids"] = sorted(episode_uuids)
    scoped_result["edges"] = scoped_edges
    scoped_result["nodes"] = scoped_nodes
    scoped_result["episodes"] = scoped_episodes
    scoped_result["results"] = filtered_results[: result.get("num_results_limit", 10)]
    scoped_result["num_results_count"] = len(scoped_result["results"])
    return scoped_result


async def simulate_search(
    config: dict,
    event: NormalizedEvent,
    num_results: int | None = None,
    group_id: str = "sentinel",
) -> dict:
    logger = get_logger("main.search")
    from graphiti.graphiti_workflow import (
        hybrid_search,
        init_graph_client,
        close_graph_client,
    )

    if num_results is None:
        num_results = int(config.get("search", {}).get("num_results", 10))

    result = {}
    graphiti = None
    subject_id_numbers = extract_subject_id_numbers(event.raw_content)
    try:
        print_info("正在初始化 Graphiti 搜索客户端...")
        graphiti = await init_graph_client(config)
        print_info("Graphiti 搜索客户端初始化完成")

        logger.info(
            "hybrid_search: query=%s, group_id=%s, num_results=%d",
            event.raw_content,
            group_id,
            num_results,
        )
        if subject_id_numbers:
            logger.info("subject_id_numbers=%s", subject_id_numbers)

        subject_episode_uuids: set[str] = set()
        if subject_id_numbers:
            subject_episode_uuids = await get_subject_episode_uuids(
                graphiti, subject_id_numbers, group_id
            )
            logger.info("subject_episode_count=%d", len(subject_episode_uuids))

        min_score = float(config.get("search", {}).get("min_score", 0.0))
        logger.info("min_score=%.2f", min_score)

        result = await asyncio.wait_for(
            hybrid_search(
                graphiti=graphiti,
                query=event.raw_content,
                group_id=group_id,
                num_results=num_results,
                min_score=min_score,
            ),
            timeout=20,
        )
        before_scope_count = len(result.get("results", [])) if result else 0
        result = filter_search_result_by_subject_episodes(
            result, subject_episode_uuids, subject_id_numbers
        )
        after_scope_count = len(result.get("results", [])) if result else 0

        print_info("搜索成功")
        if subject_id_numbers:
            logger.info(
                "subject episode filter: %d -> %d",
                before_scope_count,
                after_scope_count,
            )

        reranked_items = result.get("results", []) if result else []

        reranked_nodes = [item for item in reranked_items if item.get("type") == "node"]
        reranked_edges = [item for item in reranked_items if item.get("type") == "edge"]
        reranked_episodes = [
            item for item in reranked_items if item.get("type") == "episode"
        ]

        logger.info(
            "global_rerank_topk: total=%d, nodes=%d, edges=%d, episodes=%d",
            len(reranked_items),
            len(reranked_nodes),
            len(reranked_edges),
            len(reranked_episodes),
        )

        if result is None:
            result = {}
        result["reranked_nodes"] = reranked_nodes
        result["reranked_edges"] = reranked_edges
        result["reranked_episodes"] = reranked_episodes

    except asyncio.TimeoutError:
        print_warn("搜索超时，跳过检索")
        logger.warning("hybrid_search timed out after 20s")
        result = result or {}
        result.setdefault("reranked_nodes", [])
        result.setdefault("reranked_edges", [])
        result.setdefault("reranked_episodes", [])
    except Exception as e:
        print_error("搜索失败，跳过检索")
        logger.error("search failed: %s: %s", type(e).__name__, e)
        logger.error("stack:\n%s", traceback.format_exc())
        result = result or {}
        result.setdefault("reranked_nodes", [])
        result.setdefault("reranked_edges", [])
        result.setdefault("reranked_episodes", [])

    finally:
        if graphiti is not None:
            await close_graph_client(graphiti)
            logger.info("Graphiti client closed")

    logger.info("search complete")
    return result


# ============================================================
#  Stage 5: Dashboard — Web 看板
# ============================================================


def simulate_dashboard(
    config: dict, normalized_event: NormalizedEvent, results: dict
) -> None:
    logger = get_logger("main.dashboard")
    from providers.llm_provider import get_llm


    llm = get_llm(temperature=0.3)

    intent_analyzer = Agent(
        role="意图分析专家",
        goal="深入分析事件背后的真实意图、动机和潜在影响",
        backstory="""
        你是一个资深的意图分析专家，擅长从复杂的事件描述中挖掘真实意图。
        你的分析维度包括：
        1. 表面意图：事件直接表达的目标
        2. 深层动机：事件背后隐藏的动机
        3. 利益相关方：涉及哪些利益相关方及其立场
        4. 潜在影响：事件可能产生的短期和长期影响
        5. 信号强度：事件信号的真实性和重要性
        """,
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    trend_predictor = Agent(
        role="趋势预测专家",
        goal="基于事件意图分析，预测事件的发展趋势和可能的演变路径",
        backstory="""
        你是一个资深的趋势预测专家，擅长基于事件意图分析预测发展趋势。
        你的分析维度包括：
        1. 短期趋势（1-3个月）：事件可能的短期发展方向
        2. 中期趋势（3-12个月）：事件可能的中期演变路径
        3. 长期趋势（1年以上）：事件可能的长期影响和结局
        4. 关键转折点：预测可能影响事件走向的关键节点
        5. 概率评估：对不同发展路径的概率评估
        6. 风险预警：预测可能的风险和不确定性因素
        """,
        llm=llm,
        verbose=True,
        allow_delegation=False,
    )

    event = normalized_event
    reranked_edges = results.get("reranked_edges", []) if results else []
    reranked_episodes = results.get("reranked_episodes", []) if results else []
    context_parts = []
    for item in reranked_edges:
        text = (
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        )
        if text:
            context_parts.append(f"[edge] {text}")
    for item in reranked_episodes:
        text = (
            item.get("text")
            if isinstance(item, dict)
            else getattr(item, "content", None)
        )
        if text:
            context_parts.append(f"[episode] {text}")
    episode_context = "\n".join(context_parts)
    event_description = f"""
事件类型: {event.event_type}
风险等级: {event.risk_level} (分数: {event.risk_score})
上下文信息: {episode_context}
事件描述: {event.raw_content}
"""
    intent_task = Task(
        description=f"""
分析以下事件的意图： {event_description}

事件说明：{event_description}

请从以下维度进行深入分析：

1. **表面意图**：事件直接表达的目标是什么？
2. **深层动机**：事件背后隐藏的动机是什么？
3. **利益相关方**：涉及哪些利益相关方？他们的立场和态度是什么？
4. **潜在影响**：事件可能产生的短期和长期影响有哪些？
5. **信号强度**：该事件的信号强度如何？（高/中/低）为什么？

请使用以下格式输出分析结果：

```
# 意图分析报告

## 表面意图
[分析]

## 深层动机
[分析]

## 利益相关方
- [利益相关方1]：[立场和态度]
- [利益相关方2]：[立场和态度]

## 潜在影响
- 短期影响：[分析]
- 长期影响：[分析]

## 信号强度
[高/中/低] - [理由]
```
""",
        expected_output="一个完整的意图分析报告，包含上述所有维度的分析结果。",
        agent=intent_analyzer,
    )

    trend_task = Task(
        description=f"""
基于以下事件和意图分析，预测事件的发展趋势：

事件描述：{event_description}

请从以下维度进行趋势预测：

1. **短期趋势**（1-3个月）：事件可能的短期发展方向是什么？
2. **中期趋势**（3-12个月）：事件可能的中期演变路径是什么？
3. **长期趋势**（1年以上）：事件可能的长期影响和结局是什么？
4. **关键转折点**：预测可能影响事件走向的关键节点是什么？
5. **概率评估**：对不同发展路径的概率评估（百分比）
6. **风险预警**：预测可能的风险和不确定性因素

请使用以下格式输出分析结果：

```
# 趋势预测报告

## 短期趋势（1-3个月）
[分析]

## 中期趋势（3-12个月）
[分析]

## 长期趋势（1年以上）
[分析]

## 关键转折点
- [转折点1]：[描述]
- [转折点2]：[描述]

## 概率评估
- 路径A：[概率]
- 路径B：[概率]
- 路径C：[概率]

## 风险预警
- [风险1]：[描述]
- [风险2]：[描述]
```
""",
        expected_output="一个完整的趋势预测报告，包含上述所有维度的分析结果。",
        agent=trend_predictor,
        context=[intent_task],
    )

    crew = Crew(
        agents=[intent_analyzer, trend_predictor],
        tasks=[intent_task, trend_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    logger.info("analysis result:\n%s", result)

    print_info("Dashboard 分析完成")


# ============================================================
#  CrewAI Flow 封装
# ============================================================
#  CrewAI Agent: 将 payload 转换为 NormalizedEvent
# ============================================================


def create_normalizer_agent(llm) -> Agent:
    """创建事件标准化 Agent"""
    return Agent(
        llm=llm,
        inject_date=True,  # Automatically inject current date into tasks
        date_format="%Y-%m-%d",  # Format as "2025-03-21"
        role="事件标准化专家",
        goal="将原始消息转换为标准化的 NormalizedEvent 对象",
        backstory="你擅长从各种格式的消息中提取关键信息，并将其标准化为统一的事件格式。",
        verbose=True,
    )


def create_normalize_task(agent: Agent, raw_content: str) -> Task:
    """创建标准化任务"""
    return Task(
        name="事件标准化",
        description=f"""分析输入的内容，
        [内容]: {raw_content} 
        提取以下字段并输出 JSON:
                    - source: 数据来源 (news/chat/transaction/behavior/string)
                    - raw_content: 原始文本内容
                    - title: 事件标题
                    - timestamp: 事件发生时间（ISO格式），如果存在年月日缺失，请使用当前日期按实际情况补全，一切以原文为准。
                    不要出现markdown格式的文本
                    """,
        agent=agent,
        output_pydantic=NormalizedEvent,
        expected_output="JSON 格式的 NormalizedEvent 对象",
    )


def normalize_payload_to_event(payload: dict, config: dict) -> NormalizedEvent:
    logger = get_logger("main.normalizer")
    from providers.llm_provider import get_llm

    if isinstance(payload, NormalizedEvent):
        return payload

    raw_content = payload.get("data", json.dumps(payload))

    try:
        llm = get_llm(temperature=0.3)
        agent = create_normalizer_agent(llm)
        task = create_normalize_task(agent, raw_content)

        crew = Crew(
            agents=[agent],
            tasks=[task],
            process=Process.sequential,
            verbose=True,
        )

        result = crew.kickoff()

        result_dict = json.loads(result.raw)
        source = result_dict.get("source", "news")
        if isinstance(source, str):
            source = EventSource(source)
        # TODO: 日志记录标准化结果
        return NormalizedEvent(
            event_id=str(uuid.uuid4()),
            source=source,
            raw_content=result_dict.get("raw_content", raw_content),
            title=result_dict.get("title", ""),
            structured_data=result_dict.get("structured_data", {}),
            timestamp=result_dict.get("timestamp", datetime.now()),
            ingestion_time=result_dict.get("ingestion_time", datetime.now()),
            trace_id=result_dict.get("trace_id", ""),
            content_type=result_dict.get("content_type", "text"),
            event_type=result_dict.get("event_type", ""),
        )
    except Exception as e:
        print_error("事件标准化失败")
        logger.error("normalize_event failed: %s", e, exc_info=True)
        return NormalizedEvent(
            event_id=str(uuid.uuid4()),
            source=EventSource.NEWS,
            raw_content=raw_content,
            title="",
            structured_data={},
            timestamp=datetime.now(),
            ingestion_time=datetime.now(),
            trace_id="",
            content_type="text",
            event_type="",
        )


# ============================================================

class SentinelPipelineFlow(Flow):
    """
    Sentinel 舆情分析系统 Pipeline Flow
    """

    def __init__(self, config: dict, normalized_event=None):
        super().__init__()
        self.config = config
        self.normalized_event = normalized_event
        self._log = get_logger("main.flow")

    @start()
    def classification(self):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 1: Classification — 事件分类")
        self._log.info("=" * 60)
        self._log.info("input: event_id=%s, source=%s, content=%.80s",
                        event.event_id if event else None,
                        event.source.value if event else None,
                        event.raw_content if event else "")
        self.normalized_event = (
            simulate_classification(self.config, event) if event else None
        )
        if self.normalized_event:
            self._log.info("output: event_type=%s, entities=%s",
                            self.normalized_event.event_type,
                            list(self.normalized_event.structured_data.keys()))

    @listen(classification)
    async def graph_build(self):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 2: Graph — 知识图谱构建")
        self._log.info("=" * 60)
        self._log.info("input: event_id=%s, event_type=%s",
                        event.event_id if event else None,
                        event.event_type if event else None)
        results = await simulate_graph_build(self.config, self.normalized_event)
        result = results[0] if results else None
        self.state["graph_result"] = result
        self._log.info("output: success=%s, entities=%d, relations=%d",
                        result.get("success") if result else None,
                        result.get("entities_extracted", 0) if result else 0,
                        result.get("relations_created", 0) if result else 0)

    @listen(graph_build)
    async def risk_evaluation(self, result):
        logger = self._log
        classified_event = self.normalized_event
        logger.info("=" * 60)
        logger.info("Stage 3: Risk — 风险评估")
        logger.info("=" * 60)
        self._log.info("input: event_id=%s, risk_level=%s, risk_score=%s",
                        classified_event.event_id if classified_event else None,
                        classified_event.risk_level if classified_event else None,
                        classified_event.risk_score if classified_event else None)
        if classified_event:
            risk_result = evaluate_risk(self.config, classified_event)
            self.normalized_event.risk_level = risk_result["risk_level"]
            self.normalized_event.risk_score = risk_result["risk_score"]
            self.normalized_event.reasoning = risk_result["reasoning"]
            logger.info(
                "first risk evaluation: level=%s, score=%.2f",
                risk_result["risk_level"],
                risk_result["risk_score"],
            )
            risk_threshold = self.config["classification"]["risk_threshold"]
            if risk_result["risk_score"] > risk_threshold:
                print_info(
                    f"风险评分 {risk_result['risk_score']} 超过阈值 {risk_threshold}，进行第二次风险评估"
                )
                risk_num_results = int(
                    self.config.get("search", {}).get("risk_num_results", 20)
                )
                results = await simulate_search(
                    self.config, self.normalized_event, num_results=risk_num_results
                )
                risk_result = second_evaluate_risk(
                    self.config, classified_event, results
                )
                self.normalized_event.risk_level = risk_result["risk_level"]
                self.normalized_event.risk_score = risk_result["risk_score"]
                self.normalized_event.reasoning = risk_result["reasoning"]
                self._log.info("second evaluation output: level=%s, score=%.2f",
                                risk_result["risk_level"], risk_result["risk_score"])
            else:
                logger.info(
                    "risk_score=%.2f <= %.2f, skip second evaluation",
                    risk_result["risk_score"],
                    risk_threshold,
                )
        self._log.info("output: risk_level=%s, risk_score=%s",
                        self.normalized_event.risk_level if self.normalized_event else None,
                        self.normalized_event.risk_score if self.normalized_event else None)

        return result

    @router(risk_evaluation)
    def check_risk_and_continue(self, result):
        classified_event = self.normalized_event
        risk_level = classified_event.risk_level

        from models import RiskLevel

        if risk_level == RiskLevel.LOW:
            self._log.info("route=complete, risk_level=%s", risk_level)
            print_info("低风险事件，流程结束")
            return "complete"
        else:
            self._log.info("route=check_risk, risk_level=%s", risk_level)
            print_info("非低风险事件，进入 Search")
            return "check_risk"

    @listen("check_risk")
    async def search(self, result):
        self._log.info("=" * 60)
        self._log.info("Stage 4: Search — 混合检索")
        self._log.info("=" * 60)
        self._log.info("input: query=%.80s",
                        self.normalized_event.raw_content if self.normalized_event else "")
        results = await simulate_search(self.config, self.normalized_event)
        self._log.info("output: results_count=%d",
                        len(results.get("results", [])) if results else 0)
        return results

    @listen(search)
    def dashboard(self, results):
        self._log.info("=" * 60)
        self._log.info("Stage 5: Dashboard — 意图分析与趋势预测")
        self._log.info("=" * 60)
        self._log.info("input: results_count=%d",
                        len(results.get("results", [])) if results else 0)
        simulate_dashboard(self.config, self.normalized_event, results)
        self._log.info("output: complete")
        return "complete"

    @listen("complete")
    def end(self):
        self._log.info("pipeline finished")
        print_info("Pipeline 消息处理完成")


async def run_flow(config: dict):
    """
    使用 CrewAI Flow 运行完整 Pipeline
    从终端输入消息进行处理
    """
    print(f"\n{'=' * 70}")
    print("  Sentinel Pipeline Flow — CrewAI Flow 驱动")
    print("  输入消息进行分析 (输入 'quit' 或 'exit' 退出)")
    print(f"{'=' * 70}")

    while True:
        try:
            print("\n请输入消息内容:")
            user_input = (await asyncio.to_thread(input, "> ")).strip()

            if not user_input:
                print("消息不能为空，请重新输入")
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("退出程序")
                break

            logger = get_logger("main.flow")
            logger.info("user input: %s", user_input)

            payload = {"data": user_input}
            normalized_event = normalize_payload_to_event(payload, config)
            logger.info(
                "normalized event: event_id=%s, source=%s",
                normalized_event.event_id,
                normalized_event.source,
            )

            print_info("消息处理开始")
            flow = SentinelPipelineFlow(config, normalized_event)
            flow.kickoff()
            print_info("消息处理完成")

        except KeyboardInterrupt:
            print("\n退出程序")
            break
        except Exception as e:
            print_error("处理消息异常")
            logger = get_logger("main.flow")
            logger.error("flow exception: %s", e, exc_info=True)


# ============================================================
#  服务生命周期管理
# ============================================================


async def start_service(config: dict) -> None:
    logger = get_logger("main")
    logger.info(
        "starting full pipeline: Ingestion → Classification → Graph → Search → Dashboard"
    )
    await run_flow(config)


async def shutdown_all() -> None:
    logger = get_logger("main")
    print_banner("Shutdown — 优雅关闭")
    logger.info("shutdown: stopping all services")
    await asyncio.sleep(0.1)
    elapsed = time.time() - start_time
    print_info(f"已优雅关闭，总运行时间: {elapsed:.1f}s")
    logger.info("shutdown complete, elapsed: %.1fs", elapsed)


# ============================================================
#  入口
# ============================================================

start_time = 0.0


async def _drain_pending_asyncio_tasks() -> None:
    current = asyncio.current_task()
    pending = [t for t in asyncio.all_tasks() if t is not current and not t.done()]
    if not pending:
        return
    for task in pending:
        task.cancel()
    await asyncio.gather(*pending, return_exceptions=True)


async def main() -> None:
    global start_time
    parser = argparse.ArgumentParser(
        description="Sentinel 舆情分析系统 — Phase 1 模拟运行"
    )
    parser.add_argument(
        "--log-dir", default=None, help="日志目录，默认写入当前项目 logs/ 目录"
    )
    args = parser.parse_args()

    log_path = setup_file_logging(args.log_dir)
    try:
        start_time = time.time()

        print("╔════════════════════════════════════════════════════════════════════╗")
        print(
            "║           SENTINEL 舆情分析系统 — Phase 1 Pipeline 模拟               ║"
        )
        print("║                                                                    ║")
        print("║   Ingestion → Classification → Graph → Search → Dashboard          ║")
        print("║   RabbitMQ    CrewAI            Graphiti  Hybrid    FastAPI        ║")
        print("╚════════════════════════════════════════════════════════════════════╝")
        print(f"日志文件: {log_path}")

        config = load_config()

        try:
            await start_service(config)
        finally:
            await shutdown_all()
            await close_all_llms()
            await asyncio.sleep(0.05)
            await _drain_pending_asyncio_tasks()

        print("\n✓ Pipeline 模拟完成")
        print(f"日志文件: {log_path}")
    finally:
        logging.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
