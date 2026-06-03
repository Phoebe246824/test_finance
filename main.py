"""
Sentinel 舆情分析系统 — Pipeline 主入口
=========================================
用户输入 / 外部 payload → 黑名单过滤 → 分类 → 图谱 → 搜索 → Dashboard。

调用方式:
  uv run main.py
"""

import argparse
import asyncio
import json
import logging
import os
import time
import traceback
import uuid
from datetime import datetime

from dotenv import load_dotenv
from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start
from redis.asyncio import Redis

from blacklist.filter import BlacklistFilter
from blacklist.milvus_stash import MilvusStashStore
from blacklist.store import BlacklistStore
from graphiti.graphiti_workflow import (
    add_event_to_graph,
    batch_add_to_graph,
    close_graph_client,
    hybrid_search,
    init_graph_client,
)
from log_utils import (
    get_logger,
    print_banner,
    print_error,
    print_info,
    print_warn,
    setup_file_logging,
)
from models import (
    EventSource,
    NormalizedEvent,
)
from providers.llm_provider import close_all_llms, get_llm
from trend_prediction.classifier import EventClassifier
from trend_prediction.task_templates import (
    get_intent_analysis_task,
    get_trend_prediction_task,
)
from utils.text import extract_person_id_numbers, extract_subject_id_numbers

load_dotenv()

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
            "dry_run": os.getenv("GRAPHITI_DRY_RUN", "").lower()
            in ("1", "true", "yes"),
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
        "redis": {
            "host": os.getenv("REDIS_HOST") or "localhost",
            "port": int(os.getenv("REDIS_PORT") or "6379"),
            "password": os.getenv("REDIS_PASSWORD") or "",
            "blacklist_db": int(os.getenv("BLACKLIST_REDIS_DB") or "1"),
        },
        "milvus": {
            "uri": os.getenv("MILVUS_URI") or "http://localhost:19530",
            "token": os.getenv("MILVUS_TOKEN") or "",
            "stash_collection": os.getenv("MILVUS_STASH_COLLECTION")
            or "stashed_events",
            "stash_ttl_days": int(os.getenv("KV_TTL_DAYS") or "90"),
            "semantic_top_k": int(os.getenv("STASH_SEMANTIC_TOP_K") or "10"),
            "max_per_person": int(os.getenv("BATCH_MAX_PER_PERSON") or "20"),
            "embedding_dim": int(os.getenv("EMBEDDING_DIM") or "1024"),
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


def sanitize_text_input(text: str) -> str:
    """清洗非法 Unicode、零宽字符和不可见控制字符。"""
    cleaned = text.encode("utf-8", errors="ignore").decode("utf-8")
    zero_width = "​‌‍﻿⁠"
    for char in zero_width:
        cleaned = cleaned.replace(char, "")
    return "".join(char for char in cleaned if ord(char) >= 32 or char in "\n\r\t")


# (Ingestion 由外部消息源或用户输入触发，不再使用模拟接入)


# ============================================================
#  Stage 2: Classification — CrewAI 分类评级
# ============================================================


async def classify_event(config: dict, normalized_event: dict) -> dict:
    logger = get_logger("main.classification")

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

    result = await crew.kickoff_async(
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


def _build_related_events_context(results: dict | None) -> str:
    reranked_edges = results.get("reranked_edges", []) if results else []
    reranked_episodes = results.get("reranked_episodes", []) if results else []
    related_parts = []

    for item in reranked_edges:
        text = (
            item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        )
        if text:
            related_parts.append(f"[edge] {text}")
    for item in reranked_episodes:
        text = (
            item.get("text")
            if isinstance(item, dict)
            else getattr(item, "content", None)
        )
        if text:
            related_parts.append(f"[episode] {text}")
    return "\n".join(related_parts)


async def evaluate_risk(
    config: dict, event: NormalizedEvent, results: dict | None = None
) -> dict:
    logger = get_logger("main.risk_evaluation")

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

    related_events = _build_related_events_context(results)
    risk_task = Task(
        name="风险评估",
        description="基于事件信息从人物、物品、组织、地点、事件、重要时间等各角度，进行高标准的评估风险等级，不能忽略任何细微的风险。核心评估原则：物品、组织本身无善恶、不主动害人，但人可利用物品或组织实施伤人、滋事、违法、肇事等行为，只要存在被恶意利用、不当使用、违规流转的可能性，该物品及关联行为一律纳入风险研判，不做无风险默认化判定。示例逻辑参照：普通菜刀本身是生活用具无危害，但人可网购、持有、携带、改用菜刀伤人、寻衅滋事，因此网购菜刀、私下持有刀具、陌生人员购置锐器等场景必须研判潜在风险，不能仅按日常用品判定无风险。"
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

    result = await crew.kickoff_async(
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


async def second_evaluate_risk(
    config: dict, event: NormalizedEvent, results: dict
) -> dict:
    logger = get_logger("main.risk_evaluation")

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
    result = await crew.kickoff_async(
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


async def simulate_classification(
    config: dict, normalized_events: NormalizedEvent
) -> NormalizedEvent:
    logger = get_logger("main.classification")

    classification_result = await classify_event(config, normalized_events)

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
    graphiti = await get_graphiti_client(config)
    dry_run = config.get("graphiti", {}).get("dry_run", False)

    if dry_run:
        print_info("DRY RUN: 跳过图谱写入（提取结果仍会显示）")
        logger.info("DRY RUN mode enabled, skipping Neo4j writes")

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
            dry_run=dry_run,
        )

        entities = result.get("entities_extracted", 0)
        relations = result.get("relations_created", 0)
        if dry_run:
            print_info(
                f"提取完成（dry run，未写入数据库）: {entities} 个实体, {relations} 条关系"
            )
            logger.info(
                "DRY RUN: extraction complete, skipped Neo4j write: entities=%d, relations=%d",
                entities,
                relations,
            )
        else:
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


async def simulate_dashboard(
    config: dict, normalized_event: NormalizedEvent, results: dict
) -> None:
    logger = get_logger("main.dashboard")

    llm = get_llm(temperature=0.3)

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

    classifier = EventClassifier()
    (
        category,
        confidence,
        severity,
        severity_confidence,
    ) = await classifier.classify_with_severity(event.raw_content)
    category_name = classifier.get_category_name(category)
    severity_name = classifier.get_severity_name(severity)

    print_info(f"\n[dashboard] 事件分类: {category_name} (置信度: {confidence:.0%})")
    print_info(
        f"[dashboard] 影响严重度: {severity_name} (置信度: {severity_confidence:.0%})"
    )
    print_info("[dashboard] 使用自适应提示词进行意图分析和趋势预测")

    intent_analyzer = Agent(
        llm=llm,
        role="意图分析专家",
        goal="深入分析事件背后的真实意图、动机和潜在影响",
        backstory=(
            "你是一个资深的意图分析专家，擅长从复杂的事件描述中挖掘真实意图。"
            f"当前事件分类为「{category_name}」，请从该领域的专业视角进行分析。"
        ),
        verbose=True,
        allow_delegation=False,
    )

    trend_predictor = Agent(
        llm=llm,
        role="趋势预测专家",
        goal="基于事件意图分析，预测事件的发展趋势和可能的演变路径",
        backstory=(
            "你是一个资深的趋势预测专家，擅长基于事件意图分析预测发展趋势。"
            f"当前事件分类为「{category_name}」，影响严重度为「{severity_name}」。"
        ),
        verbose=True,
        allow_delegation=False,
    )

    intent_task = get_intent_analysis_task(
        event_text=event_description,
        classifier=classifier,
        category=category,
        confidence=confidence,
        agent=intent_analyzer,
    )

    trend_task = get_trend_prediction_task(
        event_text=event_description,
        intent_task=intent_task,
        classifier=classifier,
        category=category,
        confidence=confidence,
        agent=trend_predictor,
        severity=severity,
        severity_confidence=severity_confidence,
    )

    crew = Crew(
        agents=[intent_analyzer, trend_predictor],
        tasks=[intent_task, trend_task],
        process=Process.sequential,
        verbose=True,
    )

    result = await crew.kickoff_async()

    logger.info("analysis result:\n%s", result)

    print_info("Dashboard 分析完成")


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


async def normalize_payload_to_event(payload: dict, config: dict) -> NormalizedEvent:
    logger = get_logger("main.normalizer")

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

        result = await crew.kickoff_async()

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


async def batch_graph_event_with_related_stash(
    config: dict,
    stash_store: MilvusStashStore | None,
    id_numbers: list[str],
    normalized_event: NormalizedEvent,
) -> dict:
    logger = get_logger("main.flow")
    summary = {
        "fetched_count": 0,
        "batched_count": 0,
        "success": True,
        "batch_results": [],
    }
    if stash_store is None:
        return summary

    stash_config = config.get("milvus", {})
    historical_events = await stash_store.fetch_related_events(
        normalized_event,
        id_numbers,
        top_k_semantic=int(stash_config.get("semantic_top_k", 10)),
        max_per_person=int(stash_config.get("max_per_person", 20)),
    )
    summary["fetched_count"] = len(historical_events)
    logger.info(
        "Milvus recall fetched_count=%d event_ids=%s",
        len(historical_events),
        [event.get("event_id") for event in historical_events if event.get("event_id")],
    )

    if not historical_events:
        print_info("Milvus 暂存回捞为空，跳过批量构图")
        return summary

    print_info(f"从 Milvus 取回 {len(historical_events)} 条相关事件，执行批量构图")
    graphiti = None
    try:
        graphiti = await init_graph_client(config)
        dry_run = config.get("graphiti", {}).get("dry_run", False)

        batch_texts = []
        for historical_event in historical_events:
            reference_time = historical_event.get("created_at") or historical_event.get(
                "timestamp", datetime.now()
            )
            if isinstance(reference_time, str):
                reference_time = datetime.fromisoformat(reference_time)
            batch_texts.append(
                {
                    "text": historical_event.get("raw_content", ""),
                    "reference_time": reference_time,
                }
            )

        group_id = config.get("graphiti", {}).get("episode_source_name", "sentinel")
        batch_results = await batch_add_to_graph(
            graphiti, batch_texts, group_id, dry_run
        )
        summary["batch_results"] = batch_results
        summary["batched_count"] = len(batch_texts)

        all_success = all(r.get("success", True) for r in batch_results)
        summary["success"] = all_success
        if all_success:
            consumed_event_ids = [
                event["event_id"]
                for event in historical_events
                if event.get("event_id")
            ]
            await stash_store.mark_events_graph_built(consumed_event_ids)
            print_info("批量构图完成，已标记 Milvus 暂存事件为已构图")
        else:
            failed = sum(1 for r in batch_results if not r.get("success", True))
            print_info(
                f"批量构图部分失败 ({failed}/{len(batch_results)})，Milvus 暂存保留待重试"
            )
        return summary
    finally:
        if graphiti is not None:
            await close_graph_client(graphiti)


# ============================================================
#  CrewAI Flow 封装
# ============================================================


class SentinelPipelineFlow(Flow):
    """
    Sentinel 舆情分析系统 Pipeline Flow
    """

    def __init__(
        self,
        config: dict,
        normalized_event=None,
        redis_client=None,
        store=None,
        stash_store=None,
        id_numbers=None,
    ):
        super().__init__()
        self.config = config
        self.normalized_event = normalized_event
        self._redis_client = redis_client
        self._store = store
        self._stash_store = stash_store
        self._id_numbers = id_numbers or []
        self._log = get_logger("main.flow")

    @start()
    async def classification(self):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 1: Classification — 事件分类")
        self._log.info("=" * 60)
        self._log.info(
            "input: event_id=%s, source=%s, content=%.80s",
            event.event_id if event else None,
            event.source.value if event else None,
            event.raw_content if event else "",
        )
        self.normalized_event = (
            await simulate_classification(self.config, event) if event else None
        )
        if self.normalized_event:
            self._log.info(
                "output: event_type=%s, entities=%s",
                self.normalized_event.event_type,
                list(self.normalized_event.structured_data.keys()),
            )

    @listen(classification)
    async def single_graph_build(self):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 2: Graph — 单条构图")
        self._log.info("=" * 60)
        self._log.info(
            "input: event_id=%s, event_type=%s",
            event.event_id if event else None,
            event.event_type if event else None,
        )
        if event is None:
            self.state["graph_result"] = None
            self._log.info("output: success=%s, entities=%d, relations=%d", None, 0, 0)
            return None
        results = await simulate_graph_build(self.config, event)
        result = results[0] if results else None
        self.state["graph_result"] = result
        self._log.info(
            "output: success=%s, entities=%d, relations=%d",
            result.get("success") if result else None,
            result.get("entities_extracted", 0) if result else 0,
            result.get("relations_created", 0) if result else 0,
        )
        if (
            result
            and result.get("success")
            and self._stash_store is not None
            and event is not None
        ):
            await self._stash_store.mark_events_graph_built([event.event_id])
            self._log.info("marked current event as graph built: %s", event.event_id)
        return result

    @listen(single_graph_build)
    async def search_first_risk_context(self, result):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 3: Search — 首次风险上下文检索")
        self._log.info("=" * 60)
        if event is None:
            self.state["first_risk_context"] = {}
            return {}
        risk_num_results = int(
            self.config.get("search", {}).get("risk_num_results", 20)
        )
        context = await simulate_search(
            self.config, event, num_results=risk_num_results
        )
        self.state["first_risk_context"] = context
        return context

    @listen(search_first_risk_context)
    async def first_risk_evaluation(self, result):
        classified_event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 4: Risk — 首次风险评估")
        self._log.info("=" * 60)
        self._log.info(
            "input: event_id=%s, risk_level=%s, risk_score=%s",
            classified_event.event_id if classified_event else None,
            classified_event.risk_level if classified_event else None,
            classified_event.risk_score if classified_event else None,
        )
        if classified_event:
            risk_result = await evaluate_risk(
                self.config, classified_event, self.state.get("first_risk_context")
            )
            self.normalized_event.risk_level = risk_result["risk_level"]
            self.normalized_event.risk_score = risk_result["risk_score"]
            self.normalized_event.reasoning = risk_result["reasoning"]
            self._log.info(
                "first risk evaluation: level=%s, score=%.2f",
                risk_result["risk_level"],
                risk_result["risk_score"],
            )
        self._log.info(
            "output: risk_level=%s, risk_score=%s",
            self.normalized_event.risk_level if self.normalized_event else None,
            self.normalized_event.risk_score if self.normalized_event else None,
        )
        return result

    @router(first_risk_evaluation)
    def route_post_first_risk(self, result):
        event = self.normalized_event
        if event is None:
            self._log.info("route_post_first_risk=complete, event is None")
            return "complete"
        risk_threshold = self.config["classification"]["risk_threshold"]
        if event.risk_score > risk_threshold:
            self._log.info(
                "route_post_first_risk=batch_graph, score=%.2f > %.2f",
                event.risk_score,
                risk_threshold,
            )
            return "batch_graph"
        self._log.info(
            "route_post_first_risk=complete, score=%.2f <= %.2f",
            event.risk_score,
            risk_threshold,
        )
        return "complete"

    @listen("batch_graph")
    async def batch_graph_build_from_stash(self, result):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 5: Graph — 批量补图")
        self._log.info("=" * 60)
        if event is None:
            self.state["graph_result"] = None
            return None
        batch_summary = await batch_graph_event_with_related_stash(
            self.config,
            self._stash_store,
            self._id_numbers,
            event,
        )
        self.state["graph_result"] = batch_summary
        return batch_summary

    @listen(batch_graph_build_from_stash)
    async def search_second_risk_context(self, result):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 6: Search — 二次风险上下文检索")
        self._log.info("=" * 60)
        if event is None:
            self.state["second_risk_context"] = {}
            return {}
        risk_num_results = int(
            self.config.get("search", {}).get("risk_num_results", 20)
        )
        context = await simulate_search(
            self.config, event, num_results=risk_num_results
        )
        self.state["second_risk_context"] = context
        return context

    @listen(search_second_risk_context)
    async def second_risk_evaluation_stage(self, result):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 7: Risk — 二次风险评估")
        self._log.info("=" * 60)
        if event is None:
            return result
        context = self.state.get("second_risk_context", {})
        risk_result = await second_evaluate_risk(self.config, event, context)
        self.normalized_event.risk_level = risk_result["risk_level"]
        self.normalized_event.risk_score = risk_result["risk_score"]
        self.normalized_event.reasoning = risk_result["reasoning"]
        self.state["second_risk_applied"] = True
        self._log.info(
            "second evaluation output: level=%s, score=%.2f",
            risk_result["risk_level"],
            risk_result["risk_score"],
        )
        return context

    @router(second_risk_evaluation_stage)
    def route_post_second_risk(self, result):
        event = self.normalized_event
        if event is None:
            self._log.info("route_post_second_risk=complete, event is None")
            return "complete"
        risk_threshold = self.config["classification"]["risk_threshold"]
        if event.risk_score > risk_threshold:
            self._log.info(
                "route_post_second_risk=dashboard, score=%.2f > %.2f",
                event.risk_score,
                risk_threshold,
            )
            return "go_dashboard"
        self._log.info(
            "route_post_second_risk=complete, score=%.2f <= %.2f",
            event.risk_score,
            risk_threshold,
        )
        return "complete"

    @listen("go_dashboard")
    async def dashboard(self, result):
        event = self.normalized_event
        self._log.info("=" * 60)
        self._log.info("Stage 8: Dashboard — 意图分析与趋势预测")
        self._log.info("=" * 60)
        if event is None:
            self._log.info("output: complete")
            return "complete"
        context = self.state.get("second_risk_context") or self.state.get(
            "first_risk_context"
        )
        if context is None:
            context = {}
        self._log.info(
            "input: context_results_count=%d",
            len(context.get("results", [])) if context else 0,
        )
        await simulate_dashboard(self.config, event, context)
        self._log.info("output: complete")
        return "complete"

    @listen("complete")
    def end(self):
        self._log.info("pipeline finished")
        print_info("Pipeline 消息处理完成")


async def process_message(message: str, config: dict | None = None) -> str:
    """Process one user message through the same path used by the CLI loop."""
    if config is None:
        config = load_config()

    logger = get_logger("main.flow")
    logger.info("user input: %s", message)

    payload = {"data": message}
    normalized_event = await normalize_payload_to_event(payload, config)
    logger.info(
        "normalized event: event_id=%s, source=%s",
        normalized_event.event_id,
        normalized_event.source,
    )

    # 黑名单过滤 + Milvus 暂存
    blacklist_redis_client: Redis | None = None
    try:
        blacklist_redis_client = Redis(
            host=config["redis"]["host"],
            port=config["redis"]["port"],
            password=config["redis"]["password"] or None,
            db=config["redis"]["blacklist_db"],
            decode_responses=False,
        )

        store = BlacklistStore(blacklist_redis_client)
        stash_store = MilvusStashStore.from_config(config)
        bl_filter = BlacklistFilter(store)

        id_numbers = extract_person_id_numbers(normalized_event.raw_content)
        (
            should_proceed,
            matched_persons,
            matched_keywords,
            event_hit,
        ) = await bl_filter.check(normalized_event)

        if not should_proceed:
            await stash_store.stash_event(normalized_event, id_numbers or [])
            print_info(f"EVENT_ID: {normalized_event.event_id}")
            print_info("事件未命中黑名单，已暂存到 Milvus")
            return normalized_event.event_id

        for pid in matched_persons:
            await store.append_person(pid)
        for keyword in matched_keywords:
            await store.append_keyword(keyword)
        if event_hit:
            await store.append_event(
                normalized_event.event_id,
                normalized_event.summary or normalized_event.raw_content[:200],
            )

        print_info("消息处理开始")
        flow = SentinelPipelineFlow(
            config,
            normalized_event,
            None,
            store,
            stash_store,
            id_numbers,
        )
        await flow.kickoff_async()
        print_info(f"EVENT_ID: {normalized_event.event_id}")
        print_info("消息处理完成")
        return normalized_event.event_id

    finally:
        if blacklist_redis_client is not None:
            await blacklist_redis_client.aclose()


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
            user_input = sanitize_text_input(user_input)

            if not user_input:
                print("消息不能为空，请重新输入")
                continue

            if user_input.lower() in ["quit", "exit", "q"]:
                print("退出程序")
                break

            await process_message(user_input, config)

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
        description="Sentinel 舆情分析系统 — Pipeline 主入口"
    )
    parser.add_argument(
        "--log-dir", default=None, help="日志目录，默认写入当前项目 logs/ 目录"
    )
    args = parser.parse_args()

    log_path = setup_file_logging(args.log_dir)
    try:
        start_time = time.time()

        print("╔════════════════════════════════════════════════════════════════════╗")
        print("║           SENTINEL 舆情分析系统 — Pipeline Flow                    ║")
        print("║                                                                    ║")
        print("║   Normalize → Blacklist → Classification → Graph → Risk → Search   ║")
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

        print("\nPipeline 处理完成")
        print(f"日志文件: {log_path}")
    finally:
        logging.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
