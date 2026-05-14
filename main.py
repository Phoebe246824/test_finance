"""
Sentinel 舆情分析系统 — Phase 1 主入口（模拟运行）
=====================================================
用 print 模拟完整 Pipeline 流程，串联 Ingestion → Classification → Graph → Dashboard。

调用方式:
  python main.py                    # 运行完整 Pipeline 模拟
  python main.py --service ingestion  # 仅模拟某
  个服务
"""
import argparse
import asyncio
import json
import os
import random
import time
import uuid
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pika

load_dotenv()
# 导入真实模型与函数
from models import (
    NormalizedEvent, EventSource, ClassifiedEvent, KeyEntity,
    to_queue_message, from_queue_message,
)
from consumer import (
    normalize_event, is_duplicate, reset_duplicate_cache,
    setup_logger,
)
from crewai.flow.flow import Flow, listen, start, router
from crewai import Agent, Task, Crew, Process


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
            "host": os.getenv("RABBITMQ_HOST", "localhost"),
            "port": int(os.getenv("RABBITMQ_PORT", "5672")),
            "user": os.getenv("RABBITMQ_USER", "guest"),
            "password": os.getenv("RABBITMQ_PASSWORD", "guest"),
        },
        "neo4j": {
            "uri": os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            "user": os.getenv("NEO4J_USER", "neo4j"),
            "password": os.getenv("NEO4J_PASSWORD", "password"),
        },
        "llm": {
            "api_key": os.getenv("LLM_API_KEY", ""),
            "base_url": os.getenv("LLM_BASE_URL", "https://api.siliconflow.cn/v1"),
            "model": os.getenv("LLM_MODEL", "mimo-v2.5-pro"),
        },
        "embedder": {
            "model": os.getenv("EMBEDDER_MODEL", "BAAI/bge-m3"),
            "api_base": os.getenv("EMBEDDER_API_BASE", "https://api.siliconflow.cn/v1"),
        },
        "graphiti": {
            "episode_source_name": "sentinel",
        },
        "classification": {
            "risk_threshold": float(os.getenv("RISK_THRESHOLD", "0.2")),
        },
    }
    print("[config] 配置加载完成 (env > .env > defaults)")
    print(f"         rabbitmq:  {config['rabbitmq']['host']}:{config['rabbitmq']['port']}")
    print(f"         neo4j:     {config['neo4j']['uri']}")
    print(f"         llm:       {config['llm']['model']}")
    print(f"         embedder:  {config['embedder']['model']}")
    return config


# ============================================================
#  模拟数据工厂
# ============================================================

# 模拟的原始事件池
MOCK_RAW_EVENTS = [
    {"source": "news", "content": "某科技公司因产品质量问题被监管部门立案调查，股价暴跌15%", "title": "科技巨头遭调查"},
    {"source": "news", "content": "国务院发布新一轮数字经济扶持政策，重点支持人工智能和量子计算领域", "title": "数字经济新政策"},
    {"source": "chat", "content": "用户A: 这个App更新后闪退严重\n用户B: 我也是，客服说在修了\n用户C: 已经三天了还没修好", "title": "App闪退投诉"},
    {"source": "news", "content": "某知名企业家在公开场合发表不当言论，引发社交媒体热议和品牌抵制", "title": "企业家不当言论"},
    {"source": "transaction", "content": "账户T001向账户T002转账500万元，触发大额交易预警", "title": "大额转账预警"},
    {"source": "behavior", "content": "用户U123在24小时内访问了12个竞争对手网站并下载3份报价单", "title": "异常访问行为"},
    {"source": "news", "content": "某新能源企业电池工厂发生火灾事故，附近居民紧急疏散", "title": "电池工厂火灾"},
    {"source": "chat", "content": "员工E001: 公司下个月可能裁员30%\n员工E002: 哪来的消息？\n员工E001: HR部门的朋友说的", "title": "裁员传闻"},
    {"source": "news", "content": "央行宣布下调存款准备金率0.5个百分点，释放长期流动性约1万亿元", "title": "央行降准"},
    {"source": "transaction", "content": "账户T003连续7天在同一商户消费，每日金额递增，疑似洗钱行为", "title": "可疑交易模式"},
]

# 模拟原始事件（结构化格式，对应不同 source 的特有字段）
MOCK_RAW_EVENTS_STRUCTURED = [
    {   # 新闻 结构化
        "source": "news",
        "content": "某科技公司因产品质量问题被监管部门立案调查，股价暴跌15%",
        "title": "科技巨头遭调查",
        "author": "财经日报",
        "url": "https://news.example.com/tech-investigation",
        "source_name": "财经日报",
        "timestamp": datetime.now() - timedelta(hours=2),
    },
    {   # 聊天 结构化
        "source": "chat",
        "content": "用户A: 这个App更新后闪退严重\n用户B: 我也是",
        "title": "App闪退投诉",
        "platform": "WeChat",
        "participants": ["用户A", "用户B", "用户C"],
        "channel_id": "group_12345",
        "timestamp": datetime.now() - timedelta(hours=1),
    },
    {   # 交易 结构化
        "source": "transaction",
        "content": "账户T001向账户T002转账500万元，触发大额交易预警",
        "title": "大额转账预警",
        "from_account": "T001",
        "to_account": "T002",
        "amount": 5000000,
        "currency": "CNY",
        "timestamp": datetime.now() - timedelta(minutes=30),
    },
    {   # 行为 结构化
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
    print("\n" + "=" * 70)
    print("  Stage 1: Ingestion — 事件接入服务（调用真实函数）")
    print("=" * 70)

    # 1.1 初始化 RabbitMQ 连接
    print("\n[ingestion] 初始化 RabbitMQ 连接...")
    print(f"            host={config['rabbitmq']['host']}:{config['rabbitmq']['port']}")
    print("            连接成功 ✓ ")


    # 1.3 重置去重缓存（保证每次模拟独立）
    reset_duplicate_cache()

    # 1.4 消费事件并标准化（调用真实函数）
    normalized_events = []

    for i in range(event_count):
        raw = generate_mock_raw_event()
        source = raw["source"]

        print(f"\n[ingestion] #{i+1} 消费 raw event (source={source})")
        print(f"            title: {raw['title']}")
        print(f"            content: {raw['content'][:50]}...")

        # --- 调用normalize_event() ---
        print(f"            → normalize_event() 处理中...")
        normalized = normalize_event(raw, source)

        # --- 调用真实的 is_duplicate() ---
        if is_duplicate(normalized.event_id):
            print(f"            ✗ is_duplicate() = True, 事件 {normalized.event_id} 重复，跳过")
            continue

        print(f"            ✓ normalize_event() → event_id={normalized.event_id}")
        print(f"                               trace_id={normalized.trace_id}")
        print(f"                               source={normalized.source.value}")
        print(f"                               content_type={normalized.content_type}")
        print(f"                               structured_data keys: {list(normalized.structured_data.keys())}")

        normalized_events.append(normalized)

        # 发布到下游队列
        message = to_queue_message(normalized, "normalized", normalized.trace_id)
        print(f"            → publish to sentinel.internal.normalized ✓ ")
        print(f"              message size: {len(json.dumps(message, ensure_ascii=False))} bytes")

    print(f"\n[ingestion] 完成: 共处理 {len(normalized_events)} 条事件, "
          f"去重跳过 {event_count - len(normalized_events)} 条")
    return normalized_events


# ============================================================
#  Stage 2: Classification — CrewAI 分类评级
# ============================================================

def classify_event(config: dict, normalized_event: dict) -> dict:
    """
    事件分类 Crew：识别事件类型并提取关键实体

    Args:
        config: 全局配置
        normalized_event: 标准化事件

    Returns:
        dict: 包含 event_type, key_entities, summary 的字典
    """
    from providers.llm_provider import get_llm, close_all_llms

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

    result = crew.kickoff(inputs={
        "event_content": f"标题: {title}\n内容: {raw_content}",
    })

    try:
        result_text = str(result.raw)      
        result_dict = json.loads(result_text)

        return {
            "event_type": result_dict.get("event_type", "信息传播"),
            "key_entities": result_dict.get("key_entities", {}),
            "summary": result_dict.get("summary", ""),
        }
    except Exception as e:
        print(f"              解析分类结果失败: {e}")
        return None


def evaluate_risk(config: dict, event: NormalizedEvent) -> dict:
    """
    风险评估 Crew：评估事件的风险等级和分数

    Args:
        config: 全局配置
        event: 事件

    Returns:
        dict: 包含 risk_level, risk_score, reasoning 的字典
    """
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

    result = crew.kickoff(inputs={
        "event_type": event.event_type,
        "summary": event.summary,
        "entities": str(event.structured_data),
        "event_date": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "source": event.source,
    })

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
        print(f"              解析风险评估结果失败: {e}")
        return {
            "risk_level": "medium",
            "risk_score": 0.5,
            "reasoning": "自动评估",
        }

def second_evaluate_risk(config: dict, event: NormalizedEvent, results: dict) -> dict:
    """
    风险评估 Crew：评估事件的风险等级和分数

    Args:
        config: 全局配置
        event: 事件

    Returns:
        dict: 包含 risk_level, risk_score, reasoning 的字典
    """
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
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text:
            related_events_parts.append(f"[edge] {text}")
    for item in reranked_episodes:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "content", None)
        if text:
            related_events_parts.append(f"[episode] {text}")

    related_events = "\n".join(related_events_parts)
    risk_task = Task(
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

    print("开始第二次风险评估")
    result = crew.kickoff(inputs={
        "event_type": event.event_type,
        "summary": event.summary,
        "entities": str(event.structured_data),
        "event_date": event.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "source": event.source,
        "related_events": related_events,
    })

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
        print(f"第二次风险评估完成: risk_level=\"{final_result['risk_level']}\", risk_score={final_result['risk_score']}")
        return final_result
    except Exception as e:
        print(f"              解析风险评估结果失败: {e}")
        return {
            "risk_level": "medium",
            "risk_score": 0.5,
            "reasoning": "自动评估",
        }


def simulate_classification(config: dict, normalized_events: NormalizedEvent) -> NormalizedEvent:
    """
    分类评级服务：使用 CrewAI Agent 进行事件分类

    Args:
        config: 全局配置
        normalized_events: 标准化事件

    Returns:
        NormalizedEvent: 分类后的标准化事件
    """
    print("\n" + "=" * 70)
    print("  Stage 2: Classification — CrewAI 事件分类")
    print("=" * 70)

    classification_result = classify_event(config, normalized_events)

    event_type = classification_result["event_type"]
    key_entities = classification_result["key_entities"]
    summary = classification_result["summary"]

    print(f"              分类结果: event_type=\"{event_type}\", entities={len(key_entities)}")

    normalized_events.event_type = event_type
    normalized_events.structured_data = key_entities
    normalized_events.summary = summary
    
    print(f"\n[classifier] 完成事件分类")
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
    print("\n" + "=" * 70)
    print("  Stage 3: Graph — Graphiti 知识图谱构图")
    print("=" * 70)
    from graphiti.graphiti_workflow import add_event_to_graph

    graphiti = await get_graphiti_client(config)

    print("\n[graph] 初始化 Graphiti 客户端...")
    print(f"         Neo4j:     {config['neo4j']['uri']}")
    print(f"         LLM:       {config['llm']['model']} (实体/关系提取)")
    print(f"         Embedder:  {config['embedder']['model']} (向量检索)")
    print("         初始化完成 ✓")

    build_results = []

    print(f"\n[graph] 写入 event_id={event.event_id}")

    timestamp = event.timestamp

    try:
        result = await add_event_to_graph(
            graphiti=graphiti,
            event_text=event.raw_content,
            reference_time=timestamp,
            source_description=f"{event.source}:{event.event_type}",
        )

        print(f"         写入成功 ✓")
        print(f"             entities_extracted: {result.get('entities_extracted', 0)}")
        print(f"             relations_created: {result.get('relations_created', 0)}")

        build_results.append({
            "event_id": event.event_id,
            "success": True,
            "entities_extracted": result.get("entities_extracted", 0),
            "relations_created": result.get("relations_created", 0),
        })

    except Exception as e:
        print(f"         写入失败: {e}")
        build_results.append({
            "event_id": event.event_id,
            "success": False,
            "error": str(e),
        })
    finally:
        total_nodes = sum(r.get("entities_extracted", 0) for r in build_results)
        total_edges = sum(r.get("relations_created", 0) for r in build_results)
        print(f"\n[graph] 构图完成: {len(build_results)} 条 Episode 写入成功")
        print(f"         累计: {total_nodes} 个实体节点, {total_edges} 条关系边")

        await graphiti.close()

    return build_results


# ============================================================
#  Stage 4: Search — 混合搜索演示
# ============================================================

async def simulate_search(config: dict, event: NormalizedEvent, num_results: int = 10) -> None:
    """
    Graphiti 混合搜索：使用 Graphiti 客户端进行搜索
    """
    print("\n" + "=" * 70)
    print("  Stage 4: Search — Graphiti 混合搜索演示")
    print("=" * 70)
    from graphiti.graphiti_workflow import hybrid_search, init_graph_client

    result = {}
    graphiti = None
    try:
        print("[search] 正在初始化 Graphiti 搜索客户端...")
        graphiti = await init_graph_client(config)
        print("[search] 初始化 Graphiti 搜索客户端 ✓")

        print(f"\n[search] hybrid_search()")
        print(f"         query=\"{event.raw_content}\"")
        print(f"         group_id=sentinel")
        print(f"         num_results={num_results}")

        print("[search] 开始执行 hybrid_search...")
        result = await asyncio.wait_for(
            hybrid_search(
                graphiti=graphiti,
                query=event.raw_content,
                num_results=num_results,
            ),
            timeout=20,
        )

        print(f"         搜索成功 ✓")

        # 使用 graphiti_workflow.hybrid_search 的全局重排结果（results）
        # results 内每条形如: {"type": "edge|episode|node", "text": ..., "score": ...}
        reranked_items = result.get("results", []) if result else []

        reranked_nodes = [item for item in reranked_items if item.get("type") == "node"]
        reranked_edges = [item for item in reranked_items if item.get("type") == "edge"]
        reranked_episodes = [item for item in reranked_items if item.get("type") == "episode"]

        print(f"             [global_rerank_topk] total: {len(reranked_items)}")
        print(f"             [global_rerank_topk] nodes: {len(reranked_nodes)} 个")
        print(f"             [global_rerank_topk] edges: {len(reranked_edges)} 条")
        print(f"             [global_rerank_topk] episodes: {len(reranked_episodes)} 条")

        # 为下游保留按全局重排划分后的结果
        if result is None:
            result = {}
        result["reranked_nodes"] = reranked_nodes
        result["reranked_edges"] = reranked_edges
        result["reranked_episodes"] = reranked_episodes

    except asyncio.TimeoutError:
        print("         搜索超时: hybrid_search 超过 20 秒，跳过检索并继续第二次风险评估")
        # 保证下游第二次风险评估可继续执行
        result = result or {}
        result.setdefault("reranked_nodes", [])
        result.setdefault("reranked_edges", [])
        result.setdefault("reranked_episodes", [])
    except Exception as e:
        print(f"         搜索失败: {e}")
        # 保证下游第二次风险评估可继续执行
        result = result or {}
        result.setdefault("reranked_nodes", [])
        result.setdefault("reranked_edges", [])
        result.setdefault("reranked_episodes", [])

    finally:
        if graphiti is not None:
            await graphiti.close()
            print("[search] Graphiti 客户端已关闭")

    print(f"\n[search] 搜索完成")
    return result


# ============================================================
#  Stage 5: Dashboard — Web 看板
# ============================================================


def simulate_dashboard(config: dict, normalized_event: NormalizedEvent, results: dict) -> None:
    """
    Dashboard 阶段：意图分析 + 趋势预测
    """
    from providers.llm_provider import get_llm

    print("\n" + "=" * 70)
    print("  Stage 6: Dashboard — 意图分析 + 趋势预测")
    print("=" * 70)


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
        text = item.get("text") if isinstance(item, dict) else getattr(item, "text", None)
        if text:
            context_parts.append(f"[edge] {text}")
    for item in reranked_episodes:
        text = item.get("text") if isinstance(item, dict) else getattr(item, "content", None)
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
        agent=intent_analyzer
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
        context=[intent_task]
    )


    crew = Crew(
        agents=[intent_analyzer, trend_predictor],
        tasks=[intent_task, trend_task],
        process=Process.sequential,
        verbose=True,
    )

    result = crew.kickoff()

    print(f"\n[dashboard] 分析结果:")
    print("=" * 70)
    print(result)
    print("=" * 70)

    print(f"\n[dashboard] 分析完成")


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


def create_normalize_task(agent: Agent,raw_content: str) -> Task:
    """创建标准化任务"""
    return Task(
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
    """
    使用 CrewAI Agent 将 payload 转换为 NormalizedEvent
    payload 格式: {'data': 'xxxxx'}
    """
    from providers.llm_provider import get_llm
    import uuid


    if isinstance(payload, NormalizedEvent):
        return payload

    raw_content = payload.get("data", json.dumps(payload))

    llm = get_llm(temperature=0.3)
    agent = create_normalizer_agent(llm)
    task = create_normalize_task(agent,raw_content)

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


# ============================================================

class SentinelPipelineFlow(Flow):
    """
    Sentinel 舆情分析系统 Pipeline Flow

    流程: Ingestion → Classification → Graph → RiskEvaluation → (Search → Dashboard) / Complete
    - 低风险事件: 图谱构建 → 风险评估 → 完成
    - 非低风险事件: 图谱构建 → 风险评估 → Search → Dashboard
    """

    def __init__(self, config: dict, normalized_event=None):
        super().__init__()
        self.config = config
        self.normalized_event = normalized_event

    @start()
    def classification(self):
        """Stage 2: 事件分类"""
        print(f"\n[Flow] Stage 2: Classification")
        event = self.normalized_event
        self.normalized_event = simulate_classification(self.config, event) if event else None

    @listen(classification)
    async def graph_build(self):
        """Stage 3: 图谱构建"""
        print(f"\n[Flow] Stage 3: Graph Build")
        results = await simulate_graph_build(self.config, self.normalized_event)
        result = results[0] if results else None
        self.state["graph_result"] = result

    @listen(graph_build)
    async def risk_evaluation(self, result):
        """Stage 4: 风险评估"""
        print(f"\n[Flow] Stage 4: Risk Evaluation")
        classified_event = self.normalized_event
        if classified_event:
            risk_result = evaluate_risk(self.config, classified_event)
            self.normalized_event.risk_level = risk_result["risk_level"]
            self.normalized_event.risk_score = risk_result["risk_score"]
            self.normalized_event.reasoning = risk_result["reasoning"]
            print(f"第一次风险评估: risk_level=\"{risk_result['risk_level']}\", risk_score={risk_result['risk_score']}")
            risk_threshold = self.config["classification"]["risk_threshold"]
            if risk_result["risk_score"] > risk_threshold: # 人工调整阈值（配置化）
                print(f"[risk] risk_score={risk_result['risk_score']} > {risk_threshold}，进入第二次风险评估")
                print(f"==========================进行第二次风险评估，获取主体关联事件==========================")
                results = await simulate_search(self.config, self.normalized_event, num_results=10)
                risk_result = second_evaluate_risk(self.config, classified_event,results)
                self.normalized_event.risk_level = risk_result["risk_level"]
                self.normalized_event.risk_score = risk_result["risk_score"]
                self.normalized_event.reasoning = risk_result["reasoning"]
            else:
                print(f"[risk] risk_score={risk_result['risk_score']} <= {risk_threshold}，跳过第二次风险评估")

        return result

    @router(risk_evaluation)
    def check_risk_and_continue(self, result):
        """根据风险等级决定后续流程"""
        classified_event = self.normalized_event
        risk_level = classified_event.risk_level

        from  models import RiskLevel
        if risk_level == RiskLevel.LOW:
            print(f"\n[Flow] 低风险事件，流程结束")
            return "complete"
        else:
            print(f"\n[Flow] 非低风险事件，进入 Search")
            return "check_risk"

    @listen("check_risk")
    async def search(self, result):
        """Stage 5: 搜索服务（非低风险事件）"""
        print(f"\n[Flow] Stage 5: Search")
        results = await simulate_search(self.config, self.normalized_event)
        return results

    @listen(search)
    def dashboard(self, results):
        """Stage 6: Dashboard 展示"""
        print(f"\n[Flow] Stage 6: Dashboard")
        simulate_dashboard(self.config, self.normalized_event, results)
        return "complete"

    @listen("complete")
    def end(self):
        """Stage 7: 完成"""
        print(f"\n[Flow] Stage 7: Complete")
        print("============================================ 消息处理完成 =============================================")


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
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("退出程序")
                break

            print("============================================ 消息处理开始 =============================================")
            print(f"\n[Flow] 用户输入: {user_input}")

            payload = {"data": user_input}
            normalized_event = normalize_payload_to_event(payload, config)
            print(f"[Flow] 标准化事件: event_id={normalized_event.event_id}, source={normalized_event.source}")

            flow = SentinelPipelineFlow(config, normalized_event)
            flow.kickoff()

            print(f"[Flow] 消息处理完成 ✓")

        except KeyboardInterrupt:
            print("\n退出程序")
            break
        except Exception as e:
            print(f"[Flow] 处理消息异常: {e}")


# ============================================================
#  服务生命周期管理
# ============================================================

async def start_service(config: dict) -> None:
    """
    启动指定的核心服务，阻塞运行直到收到终止信号

    Args:
        service_name: 服务标识 "ingestion" | "classification" | "graph" | "all"
        config: 全局配置字典
        event_count: 模拟事件数量
    """

    print(f"\n[main] 启动完整 Pipeline (使用 CrewAI Flow): Ingestion → Classification → Graph → Search → Dashboard")
    await run_flow(config)



async def shutdown_all() -> None:
    """
    优雅关闭所有正在运行的服务
    """
    print("\n" + "=" * 70)
    print("  Shutdown — 优雅关闭")
    print("=" * 70)
    print("\n[shutdown] 收到 SIGINT 信号，开始优雅关闭...")
    print("[shutdown] 1/4 停止 RabbitMQ 消费者 (等待当前消息处理完毕)...")
    time.sleep(0.1)
    print("[shutdown]    消费者已停止 ✓")
    print("[shutdown] 2/4 关闭 Graphiti 客户端...")
    time.sleep(0.1)
    print("[shutdown]    Graphiti 已关闭 ✓")
    print("[shutdown] 3/4 关闭 Neo4j 连接...")
    time.sleep(0.1)
    print("[shutdown]    Neo4j 已断开 ✓")
    print("[shutdown] 4/4 关闭 FastAPI 服务...")
    time.sleep(0.1)
    print("[shutdown]    FastAPI 已关闭 ✓")
    print("\n[shutdown] 所有服务已优雅关闭")
    elapsed = time.time() - start_time
    print(f"[shutdown] 总运行时间: {elapsed:.1f}s")


# ============================================================
#  入口
# ============================================================

start_time = 0.0


async def main() -> None:
    global start_time
    parser = argparse.ArgumentParser(description="Sentinel 舆情分析系统 — Phase 1 模拟运行")
    
    start_time = time.time()

    print("╔════════════════════════════════════════════════════════════════════╗")
    print("║           SENTINEL 舆情分析系统 — Phase 1 Pipeline 模拟               ║")
    print("║                                                                    ║")
    print("║   Ingestion → Classification → Graph → Search → Dashboard          ║")
    print("║   RabbitMQ    CrewAI            Graphiti  Hybrid    FastAPI        ║")
    print("╚════════════════════════════════════════════════════════════════════╝")

    config = load_config()

    await start_service(config)
    await shutdown_all()
    await close_all_llms()

    print("\n✓ Pipeline 模拟完成")


if __name__ == "__main__":
    asyncio.run(main())
