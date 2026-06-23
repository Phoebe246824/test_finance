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

os.environ["COLUMNS"] = os.getenv("SENTINEL_CREWAI_WIDTH", "96")

from crewai import Agent, Crew, Process, Task
from crewai.flow.flow import Flow, listen, router, start
from rich.console import Console
from redis.asyncio import Redis

try:
    from crewai.events.utils.console_formatter import ConsoleFormatter

    _ORIGINAL_CONSOLE_FORMATTER_INIT = ConsoleFormatter.__init__

    def _init_narrow_crewai_console(self, verbose: bool = False):
        _ORIGINAL_CONSOLE_FORMATTER_INIT(self, verbose)
        self.console = Console(width=int(os.getenv("SENTINEL_CREWAI_WIDTH", "96")))

    ConsoleFormatter.__init__ = _init_narrow_crewai_console
except Exception:
    pass

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
        "risk_scoring": {
            "dimensions": {
                "customer_identity": float(
                    os.getenv("RISK_WEIGHT_CUSTOMER_IDENTITY")
                    or os.getenv("RISK_WEIGHT_PERSON")
                    or "0.15"
                ),
                "transaction_behavior": float(
                    os.getenv("RISK_WEIGHT_TRANSACTION_BEHAVIOR")
                    or os.getenv("RISK_WEIGHT_BEHAVIOR")
                    or "0.25"
                ),
                "counterparty": float(
                    os.getenv("RISK_WEIGHT_COUNTERPARTY")
                    or os.getenv("RISK_WEIGHT_ORGANIZATION")
                    or "0.20"
                ),
                "amount_velocity": float(
                    os.getenv("RISK_WEIGHT_AMOUNT_VELOCITY")
                    or os.getenv("RISK_WEIGHT_OBJECT")
                    or "0.15"
                ),
                "device_geo": float(
                    os.getenv("RISK_WEIGHT_DEVICE_GEO")
                    or os.getenv("RISK_WEIGHT_LOCATION")
                    or "0.10"
                ),
                "history_context": float(
                    os.getenv("RISK_WEIGHT_HISTORY_CONTEXT")
                    or os.getenv("RISK_WEIGHT_CONTEXT")
                    or "0.10"
                ),
                "compliance_signal": float(
                    os.getenv("RISK_WEIGHT_COMPLIANCE_SIGNAL")
                    or os.getenv("RISK_WEIGHT_TIME")
                    or "0.05"
                ),
            }
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
            "rerank_min_score": float(os.getenv("STASH_RERANK_MIN_SCORE") or "0.7"),
            "rerank_enabled": os.getenv("STASH_RERANK_ENABLED", "true").lower()
            not in ("0", "false", "no"),
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


def parse_llm_json_object(raw_output) -> dict:
    """Parse a JSON object from LLM output, including fenced Markdown JSON."""
    text = str(raw_output).strip()
    if not text:
        raise ValueError("empty LLM output")

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    except json.JSONDecodeError:
        pass

    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        fenced_text = "\n".join(lines).strip()
        if fenced_text:
            parsed = json.loads(fenced_text)
            if isinstance(parsed, dict):
                return parsed
            raise ValueError(f"expected JSON object, got {type(parsed).__name__}")

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("no JSON object found in LLM output")
    parsed = json.loads(text[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError(f"expected JSON object, got {type(parsed).__name__}")
    return parsed


def _normalize_risk_weights(config: dict) -> dict[str, float]:
    weights = config.get("risk_scoring", {}).get("dimensions", {})
    normalized = {name: max(float(weight), 0.0) for name, weight in weights.items()}
    total = sum(normalized.values())
    if total <= 0:
        return (
            {name: 1.0 / len(normalized) for name in normalized} if normalized else {}
        )
    return {name: weight / total for name, weight in normalized.items()}


def _coerce_dimension_score(value) -> float:
    if isinstance(value, dict):
        value = value.get("score", 0.0)
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return min(max(score, 0.0), 1.0)


def _risk_thresholds(config: dict | None = None) -> dict[str, float]:
    raw_thresholds = (config or {}).get("risk_scoring", {}).get("thresholds", {})
    try:
        high = float(raw_thresholds.get("high", 0.70))
    except (TypeError, ValueError):
        high = 0.70
    try:
        medium = float(raw_thresholds.get("medium", 0.35))
    except (TypeError, ValueError):
        medium = 0.35
    high = min(max(high, 0.0), 1.0)
    medium = min(max(medium, 0.0), 1.0)
    if medium > high:
        medium = high
    return {"high": high, "medium": medium}


def _risk_level_from_score(score: float, config: dict | None = None) -> str:
    thresholds = _risk_thresholds(config)
    if score >= thresholds["high"]:
        return "high"
    if score >= thresholds["medium"]:
        return "medium"
    return "low"


def build_weighted_risk_result(result_dict: dict, config: dict) -> dict:
    weights = _normalize_risk_weights(config)
    dimension_scores = result_dict.get("dimension_scores", {})
    weighted_parts = {}
    weighted_score = 0.0
    for dimension, weight in weights.items():
        score = _coerce_dimension_score(dimension_scores.get(dimension, 0.0))
        weighted_parts[dimension] = {
            "score": score,
            "weight": weight,
            "weighted_score": round(score * weight, 4),
        }
        weighted_score += score * weight

    calculated_score = round(min(max(weighted_score, 0.0), 1.0), 4)
    calculated_level = _risk_level_from_score(calculated_score, config)
    model_score = None
    model_score_raw = result_dict.get("risk_score")
    if model_score_raw is not None:
        try:
            model_score = round(min(max(float(model_score_raw), 0.0), 1.0), 4)
        except (TypeError, ValueError):
            model_score = None

    has_dimension_input = bool(dimension_scores)
    final_score = calculated_score if has_dimension_input else (model_score or calculated_score)
    final_level = _risk_level_from_score(final_score, config)

    return {
        "risk_level": final_level,
        "risk_score": final_score,
        "dimension_scores": weighted_parts,
        "calculated_risk_score": calculated_score,
        "calculated_risk_level": calculated_level,
        "model_reported_risk_score": model_score_raw,
        "model_reported_risk_level": result_dict.get("risk_level"),
        "risk_thresholds": _risk_thresholds(config),
        "risk_score_source": "calculated"
        if has_dimension_input
        else "model_reported_no_dimensions",
        "reasoning": result_dict.get("reasoning", ""),
    }


def print_blacklist_check_result(result) -> None:
    """Print a concise, user-facing blacklist decision summary."""
    event_similarity = result.event_similarity
    print_info(
        "黑名单检查结果: "
        f"{'PASS 进入后续 pipeline' if result.should_proceed else 'STASH 暂存'}"
    )
    print_info(
        "命中详情: "
        f"人员={result.matched_persons or '无'}; "
        f"关键词={result.matched_keywords or '无'}; "
        f"事件相似度={'命中' if event_similarity.hit else '未命中'} "
        f"(score={event_similarity.score:.4f}, threshold={event_similarity.threshold:.4f})"
    )
    if event_similarity.event_id or event_similarity.summary:
        print_info(
            "相似事件详情: "
            f"event_id={event_similarity.event_id or '未知'}, "
            f"summary={event_similarity.summary or '无'}"
        )


def format_risk_score(score: float | None) -> str:
    if score is None:
        return "None"
    try:
        return f"{float(score):.4f}"
    except (TypeError, ValueError):
        return str(score)


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
        "事件内容: {event_content}。 ",
        agent=type_classifier,
        output_format="json",
        expected_output="JSON 格式：{event_type:string, key_entities:object, summary:string}",
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
        result_dict = parse_llm_json_object(result.raw)

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
    weights = _normalize_risk_weights(config)
    thresholds = _risk_thresholds(config)
    dimension_instruction = "、".join(
        f"{name}(权重{weight:.2f})" for name, weight in weights.items()
    )
    threshold_instruction = (
        f">={thresholds['high']:.2f} 为 high，"
        f">={thresholds['medium']:.2f} 且 <{thresholds['high']:.2f} 为 medium，"
        f"<{thresholds['medium']:.2f} 为 low"
    )
    risk_task = Task(
        name="风险评估",
        description="基于金融风控事件信息从多个风险维度分别打分，并按给定权重公式计算最终 risk_score 和 risk_level。"
        "维度含义：customer_identity 客户身份/黑名单/实名一致性风险；transaction_behavior 交易行为是否异常；counterparty 交易对手、商户、账户风险；amount_velocity 金额、频次、分拆、资金流速风险；device_geo 设备、IP、地理位置、登录环境风险；history_context 历史交易和图谱关联风险；compliance_signal 反洗钱、涉诈、虚拟币、贷款欺诈、监管规则命中风险。"
        "核心评估原则：单笔交易可能看似正常，但如果与新开户账户、虚拟币平台、异常设备、异地登录、接近阈值分拆、投诉记录或历史暂存线索组合出现，应提升相应维度分数。不要仅凭一个字段下结论，必须结合关联事件信息和历史上下文。"
        "事件类型: {event_type}, 事件摘要: {summary}, 关键实体: {entities}，事件发生时间: {event_date},数据来源: {source}。"
        "关联事件信息: {related_events}。"
        "dimension_scores 必须包含这些维度及 0.0-1.0 分数: {dimension_instruction}。"
        "risk_score 必须等于 sum(dimension_scores[维度] * 对应权重)，risk_level 根据 risk_score 判定：{threshold_instruction}。",
        agent=risk_evaluator,
        output_format="json",
        expected_output="JSON 格式：{dimension_scores:{customer_identity:number,transaction_behavior:number,counterparty:number,amount_velocity:number,device_geo:number,history_context:number,compliance_signal:number}, risk_score:number, risk_level:string, reasoning:string}",
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
            "dimension_instruction": dimension_instruction,
            "threshold_instruction": threshold_instruction,
        }
    )

    try:
        result_dict = parse_llm_json_object(result.raw)
        return build_weighted_risk_result(result_dict, config)
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
    weights = _normalize_risk_weights(config)
    thresholds = _risk_thresholds(config)
    dimension_instruction = "、".join(
        f"{name}(权重{weight:.2f})" for name, weight in weights.items()
    )
    threshold_instruction = (
        f">={thresholds['high']:.2f} 为 high，"
        f">={thresholds['medium']:.2f} 且 <{thresholds['high']:.2f} 为 medium，"
        f"<{thresholds['medium']:.2f} 为 low"
    )
    risk_task = Task(
        name="二次风险评估",
        description="基于新增补图后的金融关联上下文，对多个风险维度分别重新打分，并给定权重公式计算最终 risk_score 和 risk_level。"
        "维度含义：customer_identity 客户身份/黑名单/实名一致性风险；transaction_behavior 交易行为是否异常；counterparty 交易对手、商户、账户风险；amount_velocity 金额、频次、分拆、资金流速风险；device_geo 设备、IP、地理位置、登录环境风险；history_context 历史交易和图谱关联风险；compliance_signal 反洗钱、涉诈、虚拟币、贷款欺诈、监管规则命中风险。"
        "核心评估原则：二次评估必须重点利用补图后的历史交易、同客户线索、同账户/同商户资金链路和语义相似事件。若历史暂存线索与当前事件形成分拆交易、资金归集、涉诈账户或贷款资料造假链条，应提升 history_context 与 compliance_signal 分数。"
        "事件类型: {event_type}, 事件摘要: {summary}, 关键实体: {entities}，事件发生时间: {event_date},数据来源: {source}。"
        "关联事件信息: {related_events}。"
        "dimension_scores 必须包含这些维度及 0.0-1.0 分数: {dimension_instruction}。"
        "risk_score 必须等于 sum(dimension_scores[维度] * 对应权重)，risk_level 根据 risk_score 判定：{threshold_instruction}。"
        "不要输出 markdown。",
        agent=risk_evaluator,
        output_format="json",
        expected_output="JSON 格式：{dimension_scores:{customer_identity:number,transaction_behavior:number,counterparty:number,amount_velocity:number,device_geo:number,history_context:number,compliance_signal:number}, reasoning:string}",
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
            "dimension_instruction": dimension_instruction,
            "threshold_instruction": threshold_instruction,
        }
    )

    try:
        result_dict = parse_llm_json_object(result.raw)
        final_result = build_weighted_risk_result(result_dict, config)
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


async def graph_episode_content_count(graphiti, content: str, group_id: str) -> int:
    records, _, _ = await graphiti.driver.execute_query(
        """
        MATCH (e:Episodic)
        WHERE e.group_id = $group_id
          AND e.content = $content
        RETURN count(e) AS content_count
        """,
        group_id=group_id,
        content=content,
        routing_="r",
    )
    if not records:
        return 0
    return int(records[0].get("content_count", 0))


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
        existing_content_count = await graph_episode_content_count(
            graphiti, event.raw_content, group_id
        )
        if existing_content_count > 0 and not dry_run:
            print_info("Neo4j 已存在该文本 Episode，跳过单条构图")
            logger.info(
                "skip graph write for existing episode: event_id=%s, group_id=%s, content_count=%d",
                event.event_id,
                group_id,
                existing_content_count,
            )
            build_results.append(
                {
                    "event_id": event.event_id,
                    "success": True,
                    "skipped": True,
                    "skip_reason": "existing_episode_content",
                    "existing_content_count": existing_content_count,
                    "entities_extracted": 0,
                    "relations_created": 0,
                }
            )
            return build_results

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
) -> dict:
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
风险等级: {event.risk_level} (分数: {format_risk_score(event.risk_score)})
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
    raw_report = getattr(result, "raw", None) or str(result)
    return {
        "category": category,
        "category_name": category_name,
        "category_confidence": confidence,
        "severity": severity,
        "severity_name": severity_name,
        "severity_confidence": severity_confidence,
        "report": raw_report,
    }


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
        output_format="json",
        expected_output="JSON 格式：{source:string, raw_content:string, title:string, timestamp:string}",
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

        result_dict = parse_llm_json_object(result.raw)
        source = result_dict.get("source", "news")
        if isinstance(source, str):
            source = EventSource(source)
        # TODO: 日志记录标准化结果
        return NormalizedEvent(
            event_id=str(uuid.uuid4()),
            source=source,
            raw_content=raw_content,
            title=result_dict.get("title", ""),
            structured_data={},
            timestamp=result_dict.get("timestamp", datetime.now()),
            ingestion_time=result_dict.get("ingestion_time", datetime.now()),
            trace_id=result_dict.get("trace_id", ""),
            content_type=result_dict.get("content_type", "text"),
            event_type="",
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


def get_shared_person_ids(
    historical_event: dict,
    current_id_numbers: list[str],
) -> list[str]:
    current_person_ids = {pid.upper() for pid in current_id_numbers}
    historical_person_ids = {
        str(pid).upper() for pid in historical_event.get("person_ids", [])
    }
    return sorted(current_person_ids.intersection(historical_person_ids))


async def rerank_historical_candidates(
    query: str,
    candidates: list[dict],
    min_score: float,
) -> dict[str, tuple[bool, str, float]]:
    if not candidates:
        return {}

    api_key = os.getenv("RERANKER_API_KEY", "")
    base_url = os.getenv("RERANKER_BASE_URL", "")
    model = os.getenv("RERANKER_MODEL", "")
    if not api_key or not base_url or not model:
        return {
            candidate.get("event_id", str(index)): (
                False,
                "reranker not configured",
                0.0,
            )
            for index, candidate in enumerate(candidates)
        }

    import httpx

    documents = [candidate.get("raw_content", "") for candidate in candidates]
    payload = {
        "model": model,
        "query": query,
        "documents": documents,
        "top_n": len(documents),
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/rerank",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()

    scores_by_index = {
        int(item.get("index", -1)): float(item.get("relevance_score", 0.0))
        for item in data.get("results", [])
        if item.get("index") is not None
    }
    results = {}
    for index, candidate in enumerate(candidates):
        score = scores_by_index.get(index, 0.0)
        passed = score >= min_score
        reason = f"rerank_score={score:.4f} {'>=' if passed else '<'} {min_score:.4f}"
        results[candidate.get("event_id", str(index))] = (passed, reason, score)
    return results


async def batch_graph_event_with_related_stash(
    config: dict,
    stash_store: MilvusStashStore | None,
    id_numbers: list[str],
    normalized_event: NormalizedEvent,
) -> dict:
    logger = get_logger("main.graph.batch")
    summary = {
        "fetched_count": 0,
        "eligible_count": 0,
        "batched_count": 0,
        "skipped_irrelevant_count": 0,
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

    print_info(
        f"从 Milvus 取回 {len(historical_events)} 条候选事件，检查相关性和是否需要批量构图"
    )
    graphiti = None
    try:
        graphiti = await init_graph_client(config)
        dry_run = config.get("graphiti", {}).get("dry_run", False)
        group_id = config.get("graphiti", {}).get("episode_source_name", "sentinel")

        rerank_enabled = bool(stash_config.get("rerank_enabled", True))
        rerank_min_score = float(stash_config.get("rerank_min_score", 0.7))
        shared_person_events = []
        rerank_candidate_events = []
        skipped_irrelevant_results = []
        for historical_event in historical_events:
            raw_content = historical_event.get("raw_content", "")
            if not raw_content:
                continue
            shared_person_ids = get_shared_person_ids(historical_event, id_numbers)
            if shared_person_ids:
                historical_event["eligibility_reason"] = (
                    f"shared_person_ids={shared_person_ids}"
                )
                shared_person_events.append(historical_event)
            else:
                rerank_candidate_events.append(historical_event)

        rerank_results = {}
        if rerank_candidate_events:
            if rerank_enabled:
                rerank_results = await rerank_historical_candidates(
                    normalized_event.raw_content,
                    rerank_candidate_events,
                    rerank_min_score,
                )
            else:
                rerank_results = {
                    candidate.get("event_id", str(index)): (
                        False,
                        "rerank disabled for non-shared-person candidate",
                        0.0,
                    )
                    for index, candidate in enumerate(rerank_candidate_events)
                }

        eligible_events = list(shared_person_events)
        for index, historical_event in enumerate(rerank_candidate_events):
            event_id = historical_event.get("event_id", str(index))
            passed, reason, score = rerank_results.get(
                event_id,
                (False, "missing rerank result", 0.0),
            )
            historical_event["rerank_score"] = score
            historical_event["eligibility_reason"] = reason
            if passed:
                eligible_events.append(historical_event)
                continue
            skipped_irrelevant_results.append(
                {
                    "event_id": historical_event.get("event_id"),
                    "success": True,
                    "skipped": True,
                    "skip_reason": "rerank_filtered_candidate",
                    "reason": reason,
                    "match_source": historical_event.get("match_source"),
                    "semantic_score": historical_event.get("semantic_score"),
                    "rerank_score": score,
                }
            )
            logger.info(
                "skip Milvus candidate by rerank: event_id=%s, reason=%s, match_source=%s, semantic_score=%s, rerank_score=%.4f",
                historical_event.get("event_id"),
                reason,
                historical_event.get("match_source"),
                historical_event.get("semantic_score"),
                score,
            )

        batch_texts = []
        events_to_graph = []
        skipped_existing_results = []
        skipped_existing_event_ids = []
        for historical_event in eligible_events:
            raw_content = historical_event.get("raw_content", "")
            existing_content_count = 0
            if not dry_run:
                existing_content_count = await graph_episode_content_count(
                    graphiti, raw_content, group_id
                )
            if existing_content_count > 0:
                event_id = historical_event.get("event_id")
                if event_id:
                    skipped_existing_event_ids.append(event_id)
                skipped_existing_results.append(
                    {
                        "event_id": event_id,
                        "success": True,
                        "skipped": True,
                        "skip_reason": "existing_episode_content",
                        "existing_content_count": existing_content_count,
                        "entities_extracted": 0,
                        "relations_created": 0,
                    }
                )
                continue

            reference_time = historical_event.get("created_at") or historical_event.get(
                "timestamp", datetime.now()
            )
            if isinstance(reference_time, str):
                reference_time = datetime.fromisoformat(reference_time)
            batch_texts.append(
                {
                    "text": raw_content,
                    "reference_time": reference_time,
                }
            )
            events_to_graph.append(historical_event)

        if skipped_irrelevant_results:
            print_info(
                f"Milvus 回捞中 {len(skipped_irrelevant_results)} 条未通过 rerank 过滤，跳过批量构图"
            )
        if skipped_existing_results:
            print_info(
                f"Milvus 回捞中 {len(skipped_existing_results)} 条已存在 Neo4j，跳过重复批量构图"
            )

        if batch_texts:
            print_info(f"{len(batch_texts)} 条历史事件需要执行批量构图")
            batch_results = await batch_add_to_graph(
                graphiti, batch_texts, group_id, dry_run
            )
        else:
            print_info("Milvus 回捞后无新增候选需要批量构图")
            batch_results = []

        all_results = [
            *skipped_irrelevant_results,
            *skipped_existing_results,
            *batch_results,
        ]
        summary["batch_results"] = all_results
        summary["eligible_count"] = len(eligible_events)
        summary["batched_count"] = len(batch_texts)
        summary["skipped_irrelevant_count"] = len(skipped_irrelevant_results)
        summary["skipped_existing_count"] = len(skipped_existing_results)

        all_success = all(
            r.get("success", True) for r in [*skipped_existing_results, *batch_results]
        )
        summary["success"] = all_success
        if all_success:
            consumed_event_ids = [
                event["event_id"] for event in events_to_graph if event.get("event_id")
            ]
            consumed_event_ids.extend(skipped_existing_event_ids)
            await stash_store.mark_events_graph_built(consumed_event_ids)
            print_info("批量构图/跳过检查完成，已标记相关 Milvus 暂存事件为已构图")
        else:
            failed = sum(1 for r in all_results if not r.get("success", True))
            print_info(
                f"批量构图部分失败 ({failed}/{len(all_results)})，Milvus 暂存保留待重试"
            )
        return summary
    except Exception as e:
        print_error(f"批量补图失败: {type(e).__name__}: {e}")
        logger.error("batch graph from stash failed: %s", e, exc_info=True)
        raise
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
            self.state["risk_result"] = risk_result
            self._log.info(
                "first risk evaluation: level=%s, score=%s, score_source=%s, calculated_score=%s",
                risk_result["risk_level"],
                format_risk_score(risk_result["risk_score"]),
                risk_result.get("risk_score_source"),
                format_risk_score(risk_result.get("calculated_risk_score")),
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
                "route_post_first_risk=batch_graph, score=%s > %.4f",
                format_risk_score(event.risk_score),
                risk_threshold,
            )
            return "batch_graph"
        self._log.info(
            "route_post_first_risk=complete, score=%s <= %.4f",
            format_risk_score(event.risk_score),
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

        batch_summary = result if isinstance(result, dict) else {}
        fetched_count = int(batch_summary.get("fetched_count") or 0)
        eligible_count = int(batch_summary.get("eligible_count") or 0)
        batched_count = int(batch_summary.get("batched_count") or 0)
        if batched_count == 0:
            self.state["skip_second_risk"] = True
            self.state["second_risk_context"] = None
            self._log.info(
                "skip second search/evaluation: fetched_count=%d, eligible_count=%d, batched_count=0",
                fetched_count,
                eligible_count,
            )
            if fetched_count == 0:
                print_info("Milvus 暂存回捞为空，跳过二次检索和二次风险评估")
            elif eligible_count == 0:
                print_info("Milvus 回捞候选均未通过过滤，跳过二次检索和二次风险评估")
            else:
                print_info(
                    "Milvus 回捞后无新增候选需要批量构图，跳过二次检索和二次风险评估"
                )
            return self.state.get("first_risk_context", {})

        self.state["skip_second_risk"] = False
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
        if self.state.get("skip_second_risk"):
            self._log.info(
                "skip second risk evaluation, keep first risk result: level=%s, score=%s",
                event.risk_level,
                format_risk_score(event.risk_score),
            )
            print_info(
                f"跳过二次风险评估，后续意图识别/趋势预测沿用首次风险分: risk_level={event.risk_level}, risk_score={format_risk_score(event.risk_score)}"
            )
            return self.state.get("first_risk_context", {})
        context = self.state.get("second_risk_context", {})
        risk_result = await second_evaluate_risk(self.config, event, context)
        self.normalized_event.risk_level = risk_result["risk_level"]
        self.normalized_event.risk_score = risk_result["risk_score"]
        self.normalized_event.reasoning = risk_result["reasoning"]
        self.state["risk_result"] = risk_result
        self.state["second_risk_applied"] = True
        self._log.info(
            "second evaluation output: level=%s, score=%s, score_source=%s, calculated_score=%s",
            risk_result["risk_level"],
            format_risk_score(risk_result["risk_score"]),
            risk_result.get("risk_score_source"),
            format_risk_score(risk_result.get("calculated_risk_score")),
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
                "route_post_second_risk=dashboard, score=%s > %.4f",
                format_risk_score(event.risk_score),
                risk_threshold,
            )
            return "go_dashboard"
        self._log.info(
            "route_post_second_risk=complete, score=%s <= %.4f",
            format_risk_score(event.risk_score),
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
        self._log.info(
            "dashboard uses risk result: level=%s, score=%s, second_risk_applied=%s",
            event.risk_level,
            format_risk_score(event.risk_score),
            bool(self.state.get("second_risk_applied")),
        )
        self.state["trend_report"] = await simulate_dashboard(self.config, event, context)
        self._log.info("output: complete")
        return "complete"

    @listen("complete")
    def end(self):
        self._log.info("pipeline finished")
        print_info("Pipeline 消息处理完成")


async def process_message(message: str, config: dict | None = None) -> str:
    """Process one user message through the same path used by the CLI loop."""
    result = await process_message_detailed(message, config)
    return result["event_id"]


async def process_message_detailed(
    message: str, config: dict | None = None
) -> dict:
    """Process one user message and return a structured summary for API callers."""
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
        blacklist_result = await bl_filter.check_with_details(normalized_event)
        print_blacklist_check_result(blacklist_result)

        if not blacklist_result.should_proceed:
            stashed_count = await stash_store.stash_event(
                normalized_event, id_numbers or []
            )
            print_info(f"EVENT_ID: {normalized_event.event_id}")
            if stashed_count:
                print_info("事件未命中黑名单，已暂存到 Milvus")
            else:
                print_info("事件未命中黑名单，Milvus 已存在相同内容，跳过重复暂存")
            return {
                "event_id": normalized_event.event_id,
                "status": "stashed",
                "risk_level": "low",
                "risk_score": 0.0,
                "summary": normalized_event.summary,
                "event_type": normalized_event.event_type,
                "dimension_scores": {},
                "trend_report": {},
                "blacklist": {
                    "decision": "STASH",
                    "matched_persons": blacklist_result.matched_persons,
                    "matched_keywords": blacklist_result.matched_keywords,
                    "event_similarity": blacklist_result.event_similarity.__dict__,
                },
                "stashed_count": stashed_count,
                "raw_content": normalized_event.raw_content,
                "title": normalized_event.title,
            }

        for pid in blacklist_result.matched_persons:
            await store.append_person(pid)
        for keyword in blacklist_result.matched_keywords:
            await store.append_keyword(keyword)
        if blacklist_result.event_hit:
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
        return {
            "event_id": normalized_event.event_id,
            "status": "analyzed",
            "risk_level": normalized_event.risk_level,
            "risk_score": normalized_event.risk_score,
            "summary": normalized_event.summary,
            "event_type": normalized_event.event_type,
            "reasoning": normalized_event.reasoning,
            "dimension_scores": flow.state.get("risk_result", {}).get(
                "dimension_scores", {}
            ),
            "trend_report": flow.state.get("trend_report", {}),
            "blacklist": {
                "decision": "PASS",
                "matched_persons": blacklist_result.matched_persons,
                "matched_keywords": blacklist_result.matched_keywords,
                "event_similarity": blacklist_result.event_similarity.__dict__,
            },
            "graph_result": flow.state.get("graph_result"),
            "second_risk_applied": bool(flow.state.get("second_risk_applied")),
            "raw_content": normalized_event.raw_content,
            "title": normalized_event.title,
        }

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
