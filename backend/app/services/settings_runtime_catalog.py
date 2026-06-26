from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[3]
ENV_EXAMPLE: Final = ROOT / ".env.example"

_ENV_PATTERN: Final = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]+)=(.*)$")
_GROUP_PATTERN: Final = re.compile(r"^\s*#\s*=+\s*(.*?)\s*=+\s*$")
_DISPLAY_ONLY_ENVS: Final = frozenset(
    {
        "SENTINEL_TARGET_PLATFORM",
        "SENTINEL_GPU_BACKEND",
        "SENTINEL_NPU_BACKEND",
        "RYZEN_AI_HOME",
    }
)
_COMPOSE_RECREATE_PREFIXES: Final = (
    "NEO4J_",
    "RABBITMQ_",
    "REDIS_",
    "MILVUS_",
    "MINIO_",
    "ATTU_",
    "STASH_",
    "BATCH_",
    "KV_",
)
_RUNTIME_IMMEDIATE_ENVS: Final = frozenset(
    {
        "RAGFLOW_ENABLED",
        "RAGFLOW_BASE_URL",
        "RAGFLOW_API_KEY",
        "RAGFLOW_DATASET_ID",
        "RAGFLOW_DATASET_IDS",
        "RAGFLOW_TOP_K",
        "RAGFLOW_SIMILARITY_THRESHOLD",
        "RAGFLOW_VECTOR_SIMILARITY_WEIGHT",
        "RAGFLOW_TIMEOUT_SECONDS",
        "RAGFLOW_MAX_CONTEXT_CHARS",
        "RAGFLOW_FAIL_OPEN",
        "SEARCH_NUM_RESULTS",
        "RISK_SEARCH_NUM_RESULTS",
        "SEARCH_MIN_SCORE",
        "RISK_THRESHOLD",
        "BLACKLIST_EVENT_SIMILARITY_THRESHOLD",
        "BLACKLIST_PERSON_MIN_HITS",
    }
)
_SECRET_MARKERS: Final = (
    "API_KEY",
    "ACCESS_KEY",
    "PASSWORD",
    "SECRET",
    "TOKEN",
)


@dataclass(frozen=True, slots=True)
class EnvField:
    env: str
    group: str
    raw_default: str
    help_text: str


_EXTRA_ENV_FIELDS: Final[tuple[EnvField, ...]] = (
    EnvField(
        env="GRAPHITI_EPISODE_SOURCE",
        group="Neo4j / Graphiti",
        raw_default="sentinel",
        help_text="Graphiti Episode source/group identifier used when writing and searching episodes.",
    ),
)


def clean_default(raw_value: str) -> str:
    stripped = raw_value.strip()
    if stripped.startswith(('"', "'")) and stripped.endswith(('"', "'")):
        return stripped[1:-1]
    return stripped


def is_list_env(env: str) -> bool:
    return env.endswith("_IDS")


def is_secret(env: str) -> bool:
    return any(marker in env for marker in _SECRET_MARKERS)


def effective_scope(env: str) -> str:
    if env in _DISPLAY_ONLY_ENVS:
        return "display_only"
    if env.startswith("VITE_"):
        return "frontend_rebuild"
    if env in _RUNTIME_IMMEDIATE_ENVS or env.startswith("RISK_WEIGHT_"):
        return "runtime_immediate"
    if env.startswith(_COMPOSE_RECREATE_PREFIXES):
        return "compose_recreate"
    return "web_restart"


def label_for(env: str) -> str:
    return env.replace("_", " ").title()


def load_env_catalog() -> list[EnvField]:
    fields: dict[str, EnvField] = {}
    group = "未分组"
    comments: list[str] = []
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if group_match := _GROUP_PATTERN.match(line):
            group = group_match.group(1).strip() or group
            comments = []
            continue
        if match := _ENV_PATTERN.match(line):
            env = match.group(1)
            fields[env] = EnvField(
                env=env,
                group=group,
                raw_default=match.group(2),
                help_text=" ".join(comments) or f"{env} runtime setting",
            )
            comments = []
            continue
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("# ="):
            comment = stripped.removeprefix("#").strip()
            if comment:
                comments.append(comment)
        elif stripped:
            comments = []
    for field in _EXTRA_ENV_FIELDS:
        fields.setdefault(field.env, field)
    return list(fields.values())
