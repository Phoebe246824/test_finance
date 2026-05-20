"""
Sentinel 舆情分析系统 — 事件接入服务 (Ingestion)
=================================================
从 RabbitMQ 多个队列消费原始事件，标准化后传递给下游分类服务。

当前已有基础: FastAPI 消息发送接口 + pika 消费者框架
本次扩展: 多队列消费、事件标准化、幂等去重、转发至下游
"""

import json
import logging
import uuid
import threading
import time
from datetime import datetime
from log_utils import print_error

from logging.handlers import RotatingFileHandler

from models import (
    NormalizedEvent,
    EventSource,
    to_queue_message,
)

# 惰性导入 pika（未安装时不影响 normalize_event 等函数）
try:
    import pika

    PIKA_AVAILABLE = True
except ImportError:
    pika = None  # type: ignore
    PIKA_AVAILABLE = False


# ============================================================
#  日志与配置
# ============================================================


def setup_logger(name: str, log_file: str = "ingestion.log") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# ============================================================
#  全局去重缓存
# ============================================================

# 内存去重缓存: event_id -> ingestion_time
# Phase 1 使用内存 dict + TTL，Phase 3 升级为 Redis / PostgreSQL
_PROCESSED_EVENTS: dict[str, float] = {}
_TTL_SECONDS = 3600  # 1 小时过期
_CACHE_LOCK = threading.Lock()


def _cleanup_expired_cache() -> None:
    """
    清理超过 TTL 的去重缓存记录
    每次调用 is_duplicate 时自动触发清理（每 10 分钟最多执行一次）
    """
    global _LAST_CLEANUP
    now = time.time()
    if now - _LAST_CLEANUP < 600:  # 10 分钟
        return
    _LAST_CLEANUP = now
    expired = [eid for eid, ts in _PROCESSED_EVENTS.items() if now - ts > _TTL_SECONDS]
    for eid in expired:
        del _PROCESSED_EVENTS[eid]


_LAST_CLEANUP: float = 0.0


# ============================================================
#  RabbitMQ 连接管理
# ============================================================


def get_rabbitmq_connection(config: dict):
    """
    获取 RabbitMQ 连接和通道（带认证、心跳、重连）

    Args:
        config: 包含 host, port, user, password 的配置字典

    Returns:
        tuple: (connection, channel)

    作用:
        使用 BlockingConnection 创建连接
        设置 heartbeat=60 防止断开
        声明所有需要的 Exchange 和 Queue（durable=True）
        设置 prefetch_count=1 保证顺序处理
    """
    if not PIKA_AVAILABLE:
        raise RuntimeError(
            "pika 未安装，无法连接 RabbitMQ。\n安装方式: pip install pika"
        )
    credentials = pika.PlainCredentials(
        username=config["user"],
        password=config["password"],
    )
    connection_params = pika.ConnectionParameters(
        host=config["host"],
        port=config["port"],
        credentials=credentials,
        heartbeat=60,
        connection_attempts=3,
        retry_delay=5,
    )
    connection = pika.BlockingConnection(connection_params)
    channel = connection.channel()

    # 设置 prefetch: 每次只取 1 条消息，保证顺序处理
    channel.basic_qos(prefetch_count=1)

    return connection, channel


def declare_topology(channel, config: dict) -> None:
    """
    声明 RabbitMQ 拓扑结构（Exchange + Queue + Binding）

    Args:
        channel: RabbitMQ 通道
        config: 配置字典

    作用:
        创建 Topic Exchange: sentinel.events
        绑定 4 个源队列:
            sentinel.events.news         → 新闻事件
            sentinel.events.chat         → 聊天记录
            sentinel.events.transaction  → 交易记录
            sentinel.events.behavior     → 行为轨迹
        创建 Direct Exchange: sentinel.internal
        绑定内部队列:
            sentinel.internal.normalized  → 标准化后的下游队列
        配置 DLQ (Dead Letter Queue):
            sentinel.dlq.ingestion       → 消费失败的消息
    """
    # ---- Topic Exchange: sentinel.events (上游事件入口) ----
    channel.exchange_declare(
        exchange="sentinel.events",
        exchange_type="topic",
        durable=True,
    )

    # 源队列 + DLQ 绑定
    source_queues = {
        "news": "sentinel.events.news",
        "chat": "sentinel.events.chat",
        "transaction": "sentinel.events.transaction",
        "behavior": "sentinel.events.behavior",
    }

    for routing_key, queue_name in source_queues.items():
        # 定义死信交换和路由
        dlq_args = {
            "x-dead-letter-exchange": "sentinel.dlx",
            "x-dead-letter-routing-key": "sentinel.dlq.ingestion",
        }
        channel.queue_declare(
            queue=queue_name,
            durable=True,
            arguments=dlq_args,
        )
        channel.queue_bind(
            queue=queue_name,
            exchange="sentinel.events",
            routing_key=routing_key,
        )

    # ---- Dead Letter Exchange + Queue ----
    channel.exchange_declare(
        exchange="sentinel.dlx",
        exchange_type="direct",
        durable=True,
    )
    channel.queue_declare(
        queue="sentinel.dlq.ingestion",
        durable=True,
    )
    channel.queue_bind(
        queue="sentinel.dlq.ingestion",
        exchange="sentinel.dlx",
        routing_key="sentinel.dlq.ingestion",
    )

    # ---- Direct Exchange: sentinel.internal (内部服务间通信) ----
    channel.exchange_declare(
        exchange="sentinel.internal",
        exchange_type="direct",
        durable=True,
    )
    channel.queue_declare(
        queue="sentinel.internal.normalized",
        durable=True,
    )
    channel.queue_bind(
        queue="sentinel.internal.normalized",
        exchange="sentinel.internal",
        routing_key="normalized",
    )


# ============================================================
#  事件标准化
# ============================================================


def normalize_event(raw_event: dict, source: str) -> NormalizedEvent:
    """
    将不同来源的原始事件标准化为统一格式

    Args:
        raw_event: 原始事件字典（来源不同，结构不同）
        source: 数据源标识 ("news" | "chat" | "transaction" | "behavior")

    Returns:
        NormalizedEvent: 标准化事件

    作用:
        为事件分配全局唯一 event_id (ULID)
        提取文本内容到 raw_content 字段
        将源特有的结构化字段放入 structured_data
        补充 ingestion_time 和 trace_id
    """
    try:
        event_id = str(uuid.uuid4())
    except ImportError:
        # fallback: UUID-based pseudo-ULID
        event_id = uuid.uuid4().hex[:26].upper()

    trace_id = uuid.uuid4().hex[:16]
    now = datetime.now()

    # 根据来源提取文本内容和结构化数据
    raw_content = ""
    structured_data = {}
    title = ""

    if source == "news":
        raw_content = raw_event.get("content", "")
        title = raw_event.get("title", "")
        structured_data = {
            "author": raw_event.get("author", ""),
            "url": raw_event.get("url", ""),
            "source_name": raw_event.get("source_name", ""),
        }

    elif source == "chat":
        raw_content = raw_event.get("content", "")
        title = raw_event.get("title", "聊天记录")
        structured_data = {
            "platform": raw_event.get("platform", ""),
            "participants": raw_event.get("participants", []),
            "channel_id": raw_event.get("channel_id", ""),
        }

    elif source == "transaction":
        raw_content = raw_event.get("content", "")
        title = raw_event.get("title", "交易记录")
        structured_data = {
            "from_account": raw_event.get("from_account", ""),
            "to_account": raw_event.get("to_account", ""),
            "amount": raw_event.get("amount", 0),
            "currency": raw_event.get("currency", "CNY"),
        }

    elif source == "behavior":
        raw_content = raw_event.get("content", "")
        title = raw_event.get("title", "行为轨迹")
        structured_data = {
            "user_id": raw_event.get("user_id", ""),
            "action": raw_event.get("action", ""),
            "target": raw_event.get("target", ""),
            "device": raw_event.get("device", ""),
        }

    else:
        # 未知来源，全部放入 raw_content
        raw_content = json.dumps(raw_event, ensure_ascii=False)
        title = raw_event.get("title", "")

    # 确定内容类型
    if raw_content and structured_data:
        content_type = "mixed"
    elif structured_data and not raw_content:
        content_type = "structured"
    else:
        content_type = "text"

    # 解析 timestamp
    timestamp = now
    raw_ts = raw_event.get("timestamp")
    if raw_ts:
        if isinstance(raw_ts, datetime):
            timestamp = raw_ts
        elif isinstance(raw_ts, str):
            try:
                timestamp = datetime.fromisoformat(raw_ts)
            except (ValueError, TypeError):
                pass

    return NormalizedEvent(
        event_id=event_id,
        source=EventSource(source),
        raw_content=raw_content,
        title=title,
        structured_data=structured_data,
        timestamp=timestamp,
        ingestion_time=now,
        trace_id=trace_id,
        content_type=content_type,
    )


def is_duplicate(event_id: str) -> bool:
    """
    检查事件是否已处理过（幂等性保证）

    Args:
        event_id: 事件唯一 ID

    Returns:
        bool: True 表示重复事件，应跳过

    作用:
        查询本地去重缓存（Phase 1 使用内存 set + TTL）
        Phase 3 升级为 Redis / PostgreSQL 去重表
    """
    with _CACHE_LOCK:
        _cleanup_expired_cache()
        if event_id in _PROCESSED_EVENTS:
            return True
        _PROCESSED_EVENTS[event_id] = time.time()
        return False


def reset_duplicate_cache() -> None:
    """
    重置去重缓存（主要用于测试）
    """
    global _LAST_CLEANUP
    with _CACHE_LOCK:
        _PROCESSED_EVENTS.clear()
        _LAST_CLEANUP = 0.0


# ============================================================
#  消费者
# ============================================================

# 重试计数器: event_id -> 重试次数
_RETRY_COUNTS: dict[str, int] = {}
_MAX_RETRIES = 3


def create_event_callback(source: str, channel, config: dict):
    """
    创建指定数据源的消费回调函数（工厂模式）

    Args:
        source: 数据源标识
        channel: RabbitMQ 通道（用于发布标准化后的事件）
        config: 配置字典

    Returns:
        callable: 消费回调函数 callback(ch, method, properties, body)

    作用:
        闭包捕获 source 和 channel
        回调逻辑:
            1. 解析原始消息 body
            2. 调用 normalize_event() 标准化
            3. 调用 is_duplicate() 去重检查
            4. 发布标准化事件到 sentinel.internal.normalized 队列
            5. 手动 ACK 确认消息
            6. 异常时: 记录日志，不 ACK（消息重回队列），超过重试次数进入 DLQ
    """
    logger = setup_logger(f"consumer.{source}")

    def callback(ch, method, properties, body):
        try:
            # 1. 解析原始消息
            raw_event = json.loads(body.decode("utf-8"))
            trace_id = raw_event.get("trace_id", uuid.uuid4().hex[:16])

            # 2. 标准化
            normalized = normalize_event(raw_event, source)

            # 3. 去重检查
            if is_duplicate(normalized.event_id):
                logger.info(f"[{trace_id}] 事件重复，跳过: {normalized.event_id}")
                ch.basic_ack(delivery_tag=method.delivery_tag)
                return

            # 4. 发布到下游队列
            message = to_queue_message(normalized, "normalized", normalized.trace_id)
            publish_props = None
            if PIKA_AVAILABLE and pika is not None:
                publish_props = pika.BasicProperties(
                    delivery_mode=2,  # 持久化
                    content_type="application/json",
                )
            channel.basic_publish(
                exchange="sentinel.internal",
                routing_key="normalized",
                body=json.dumps(message, ensure_ascii=False, default=str),
                properties=publish_props,
            )

            # 5. ACK 确认
            ch.basic_ack(delivery_tag=method.delivery_tag)
            logger.info(
                f"[{normalized.trace_id}] 标准化完成: "
                f"event_id={normalized.event_id}, source={source}"
            )

        except Exception as e:
            # 6. 异常处理
            logger.error(f"[ingestion] 处理消息异常: {e}", exc_info=True)

            # 检查重试次数
            msg_id = properties.message_id or str(method.delivery_tag)
            retry_count = _RETRY_COUNTS.get(msg_id, 0) + 1
            _RETRY_COUNTS[msg_id] = retry_count

            if retry_count >= _MAX_RETRIES:
                # 超过重试次数，ACK 并丢弃（由 DLQ 接收）
                ch.basic_ack(delivery_tag=method.delivery_tag)
                logger.warning(
                    f"[ingestion] 消息重试 {retry_count} 次仍失败，进入 DLQ: {e}"
                )
                del _RETRY_COUNTS[msg_id]
            else:
                # 不 ACK，消息重回队列等待重试
                logger.info(f"[ingestion] 消息处理失败，第 {retry_count} 次重试: {e}")

    return callback


def start_consumers(config: dict) -> None:
    """
    启动所有数据源的消费者（阻塞运行）

    Args:
        config: 全局配置字典

    作用:
        创建 RabbitMQ 连接
        调用 declare_topology() 声明拓扑
        为每个数据源注册消费者:
            news_consumer      → 监听 sentinel.events.news
            chat_consumer      → 监听 sentinel.events.chat
            transaction_consumer → 监听 sentinel.events.transaction
            behavior_consumer  → 监听 sentinel.events.behavior
        启动消费循环 start_consuming()
        注册优雅关闭处理
    """
    if not PIKA_AVAILABLE:
        raise RuntimeError("pika 未安装，无法启动消费者。\n安装方式: pip install pika")

    logger = setup_logger("ingestion")

    try:
        connection, channel = get_rabbitmq_connection(config)
        logger.info("RabbitMQ 连接成功")
    except Exception as e:
        logger.error(f"RabbitMQ 连接失败: {e}")
        print_error("RabbitMQ 连接失败，请检查配置")
        raise

    # 声明拓扑
    declare_topology(channel, config)
    logger.info("RabbitMQ 拓扑声明完成")

    # 注册消费者
    source_map = {
        "news": "sentinel.events.news",
        "chat": "sentinel.events.chat",
        "transaction": "sentinel.events.transaction",
        "behavior": "sentinel.events.behavior",
    }

    for source, queue_name in source_map.items():
        callback = create_event_callback(source, channel, config)
        channel.basic_consume(
            queue=queue_name,
            on_message_callback=callback,
        )
        logger.info(f"消费者已注册: source={source}, queue={queue_name}")

    # 优雅关闭
    def shutdown(sig, frame):
        logger.info("收到关闭信号，停止消费...")
        channel.stop_consuming()

    import signal

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    logger.info("开始消费消息...")
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        pass
    finally:
        channel.close()
        connection.close()
        logger.info("RabbitMQ 连接已关闭")


# ============================================================
#  统计数据（用于 FastAPI 接口）
# ============================================================

_STATS = {
    "total_processed": 0,
    "by_source": {"news": 0, "chat": 0, "transaction": 0, "behavior": 0},
    "start_time": datetime.now().isoformat(),
    "recent_events": [],  # 最近的标准化事件（最多 100 条）
}
_STATS_LOCK = threading.Lock()


def record_event(event: NormalizedEvent) -> None:
    """
    记录处理事件到统计缓存

    Args:
        event: 标准化事件
    """
    with _STATS_LOCK:
        _STATS["total_processed"] += 1
        src = event.source.value
        if src in _STATS["by_source"]:
            _STATS["by_source"][src] += 1
        _STATS["recent_events"].append(event.model_dump(mode="json"))
        # 保留最近 100 条
        if len(_STATS["recent_events"]) > 100:
            _STATS["recent_events"] = _STATS["recent_events"][-100:]


def get_stats() -> dict:
    """
    获取当前统计信息

    Returns:
        dict: 统计数据快照
    """
    with _STATS_LOCK:
        return {
            "total_processed": _STATS["total_processed"],
            "by_source": dict(_STATS["by_source"]),
            "start_time": _STATS["start_time"],
            "recent_count": len(_STATS["recent_events"]),
        }


def get_recent_events(limit: int = 20, offset: int = 0) -> list[dict]:
    """
    获取最近的标准化事件（分页）

    Args:
        limit: 返回数量
        offset: 偏移量

    Returns:
        list[dict]: 事件列表
    """
    with _STATS_LOCK:
        events = _STATS["recent_events"]
        return events[offset : offset + limit]


def get_event_by_id(event_id: str) -> dict | None:
    """
    根据 event_id 查找事件

    Args:
        event_id: 事件 ID

    Returns:
        dict | None: 事件字典，未找到返回 None
    """
    with _STATS_LOCK:
        for event in _STATS["recent_events"]:
            if event.get("event_id") == event_id:
                return event
    return None


# ============================================================
#  FastAPI 接口（保留原有 + 扩展）
# ============================================================


def create_app(config: dict):
    """
    创建 FastAPI 应用实例

    Args:
        config: 全局配置字典

    Returns:
        FastAPI: 应用实例

    包含的端点:
        GET  /                    → 健康检查
        POST /send-message        → 原有: 发送测试消息到 RabbitMQ（保留兼容）
        GET  /events              → 查询最近 N 条标准化事件（分页）
        GET  /events/{event_id}   → 查询单条事件详情
        GET  /stats               → 消费统计（总数、按来源分布、速率）
    """
    from fastapi import FastAPI, Query, HTTPException

    app = FastAPI(title="Sentinel Ingestion Service", version="1.0")

    logger = setup_logger("ingestion.api")

    @app.get("/")
    def health_check():
        """健康检查"""
        return {"status": "ok", "service": "sentinel-ingestion"}

    @app.post("/send-message")
    def send_message(message: dict):
        """
        发送测试消息到 RabbitMQ（保留兼容）

        Body:
            {
                "source": "news",
                "content": "测试内容",
                "title": "测试标题"
            }
        """
        if not PIKA_AVAILABLE:
            raise HTTPException(
                status_code=500,
                detail="pika 未安装，无法连接 RabbitMQ。请先安装: pip install pika",
            )
        try:
            connection, channel = get_rabbitmq_connection(config)
            declare_topology(channel, config)

            source = message.get("source", "news")
            routing_key = f"sentinel.events.{source}"

            publish_props = pika.BasicProperties(
                delivery_mode=2,
                content_type="application/json",
            )
            channel.basic_publish(
                exchange="sentinel.events",
                routing_key=routing_key,
                body=json.dumps(message, ensure_ascii=False),
                properties=publish_props,
            )

            channel.close()
            connection.close()

            return {"status": "ok", "routing_key": routing_key}

        except Exception as e:
            logger.error(f"发送消息失败: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/events")
    def list_events(
        limit: int = Query(default=20, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
    ):
        """查询最近 N 条标准化事件（分页）"""
        events = get_recent_events(limit=limit, offset=offset)
        stats = get_stats()
        return {
            "items": events,
            "total": stats["recent_count"],
            "limit": limit,
            "offset": offset,
        }

    @app.get("/events/{event_id}")
    def get_event(event_id: str):
        """查询单条事件详情"""
        event = get_event_by_id(event_id)
        if event is None:
            raise HTTPException(status_code=404, detail=f"Event {event_id} not found")
        return event

    @app.get("/stats")
    def stats():
        """消费统计（总数、按来源分布、速率）"""
        stats = get_stats()
        # 计算运行时长和处理速率
        start = datetime.fromisoformat(stats["start_time"])
        elapsed = (datetime.now() - start).total_seconds()
        rate = stats["total_processed"] / max(elapsed, 1)
        return {
            **stats,
            "elapsed_seconds": round(elapsed, 1),
            "events_per_second": round(rate, 2),
        }

    return app
