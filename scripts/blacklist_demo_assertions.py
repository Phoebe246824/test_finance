"""Reusable database-state assertions and diagnostics for the blacklist demo."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from scripts.milvus_demo_diagnostics import (
    MilvusDiagnostics,
    default_events_store,
    diagnose_milvus_failure,
)

__all__ = [
    "CASE_TEXT_PERSISTENCE_QUERY",
    "EPISODIC_CONTENT_SCHEMA_QUERY",
    "AssertionFailure",
    "MilvusCaseInspector",
    "MilvusDiagnostics",
    "Neo4jCaseInspector",
    "assert_case_state",
    "collect_case_state_snapshot",
    "diagnose_milvus_failure",
]

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


# ── Diagnostics ──────────────────────────────────────────────────────────


CASE_TEXT_PERSISTENCE_QUERY = """
MATCH (e:Episodic)
WHERE e.content = $content
RETURN count(e) AS content_count
"""

EPISODIC_CONTENT_SCHEMA_QUERY = """
CALL db.labels() YIELD label
WITH collect(label) AS labels
CALL db.propertyKeys() YIELD propertyKey
WITH labels, collect(propertyKey) AS property_keys
RETURN 'Episodic' IN labels AS episodic_label_exists,
       'content' IN property_keys AS content_property_exists
"""


@dataclass(frozen=True)
class AssertionFailure:
    case_id: str
    path: str
    expected: Any
    observed: Any


def assert_case_state(case: dict[str, Any], observed: dict[str, Any]) -> list[AssertionFailure]:
    expected = case.get("expect_state", {})
    case_id = case["id"]
    failures: list[AssertionFailure] = []
    failures.extend(_assert_expected_for_case(case_id, expected, observed))

    for related_case_id, related_expected in expected.get("after_case", {}).items():
        failures.extend(_assert_expected_for_case(related_case_id, related_expected, observed))

    return failures


def _assert_expected_for_case(
    case_id: str,
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> list[AssertionFailure]:
    state = observed.get("cases", {}).get(case_id, {})
    failures: list[AssertionFailure] = []

    milvus_expected = expected.get("milvus", {})
    milvus_state = state.get("milvus", {})
    for key in ("exists", "person_ids", "is_graph_built"):
        if key in milvus_expected:
            observed_value = milvus_state.get(key)
            expected_value = milvus_expected[key]
            if key == "person_ids" and observed_value is not None:
                observed_value = sorted(observed_value)
                expected_value = sorted(expected_value)
            if observed_value != expected_value:
                failures.append(AssertionFailure(case_id, f"milvus.{key}", expected_value, observed_value))

    neo4j_expected = expected.get("neo4j", {})
    neo4j_state = state.get("neo4j", {})
    if "content_count" in neo4j_expected and neo4j_state.get("content_count") != neo4j_expected["content_count"]:
        failures.append(
            AssertionFailure(
                case_id,
                "neo4j.content_count",
                neo4j_expected["content_count"],
                neo4j_state.get("content_count"),
            )
        )
    if "content_count_at_most" in neo4j_expected:
        observed_count = neo4j_state.get("content_count")
        if observed_count is None or observed_count > neo4j_expected["content_count_at_most"]:
            failures.append(
                AssertionFailure(
                    case_id,
                    "neo4j.content_count_at_most",
                    neo4j_expected["content_count_at_most"],
                    observed_count,
                )
            )
    if neo4j_expected.get("no_duplicate_content") is True and neo4j_state.get("duplicate_content") is True:
        failures.append(AssertionFailure(case_id, "neo4j.no_duplicate_content", True, False))

    return failures


async def collect_case_state_snapshot(
    cases: list[dict[str, Any]],
    milvus_inspector: Any | None = None,
    neo4j_inspector: Any | None = None,
) -> dict[str, Any]:
    milvus_inspector = milvus_inspector or MilvusCaseInspector()
    neo4j_inspector = neo4j_inspector or Neo4jCaseInspector()
    snapshot: dict[str, Any] = {"cases": {}}
    for case in cases:
        snapshot["cases"][case["id"]] = {
            "milvus": await milvus_inspector.inspect_case(case),
            "neo4j": await neo4j_inspector.inspect_case(case),
        }
    return snapshot


class MilvusCaseInspector:
    def __init__(self, store: Any | None = None):
        self._store = store or self._create_store_from_env()

    @staticmethod
    def _create_store_from_env() -> Any:
        return default_events_store()

    async def inspect_case(self, case: dict[str, Any]) -> dict[str, Any]:
        event_id = case.get("event_id")
        if not event_id:
            return {"exists": False, "person_ids": [], "is_graph_built": None}

        rows = self._store.query_event_rows(
            event_id,
            ["event_id", "person_ids", "is_graph_built"],
        )
        if not rows:
            return {"exists": False, "person_ids": [], "is_graph_built": None}
        row = rows[0]
        return {
            "exists": True,
            "person_ids": sorted(row.get("person_ids") or []),
            "is_graph_built": row.get("is_graph_built"),
            "event_id": row.get("event_id"),
        }

class Neo4jCaseInspector:
    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
        driver_factory: Any | None = None,
    ):
        self._uri = uri or os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self._user = user or os.getenv("NEO4J_USER", "neo4j")
        self._password = password or os.getenv("NEO4J_PASSWORD")
        self._database = database or os.getenv("NEO4J_DATABASE")
        self._driver_factory = driver_factory

    async def inspect_case(self, case: dict[str, Any]) -> dict[str, Any]:
        from neo4j import AsyncGraphDatabase

        if not self._password:
            raise RuntimeError("NEO4J_PASSWORD is required for demo state validation")

        driver_factory = self._driver_factory or AsyncGraphDatabase.driver
        driver = driver_factory(self._uri, auth=(self._user, self._password))
        try:
            async with driver.session(database=self._database) as session:
                schema_result = await session.run(EPISODIC_CONTENT_SCHEMA_QUERY)
                schema_record = await schema_result.single() or {}
                episodic_label_exists = bool(schema_record.get("episodic_label_exists"))
                content_property_exists = bool(schema_record.get("content_property_exists"))

                if episodic_label_exists and content_property_exists:
                    result = await session.run(
                        CASE_TEXT_PERSISTENCE_QUERY,
                        content=case["text"],
                    )
                    record = await result.single()
                    content_count = int(record["content_count"] if record else 0)
                else:
                    content_count = 0
        finally:
            await driver.close()

        return {
            "content_count": content_count,
            "duplicate_content": content_count > 1,
            "episodic_label_exists": episodic_label_exists,
            "content_property_exists": content_property_exists,
        }
