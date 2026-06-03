import pytest

from scripts.blacklist_demo_assertions import (
    AssertionFailure,
    MilvusCaseInspector,
    assert_case_state,
    collect_case_state_snapshot,
)


def test_assert_case_state_accepts_matching_milvus_and_neo4j_state():
    case = {
        "id": "case_a",
        "expect_state": {
            "milvus": {"exists": True, "person_ids": ["P01"], "is_graph_built": False},
            "neo4j": {"content_count": 0},
        },
    }
    observed = {
        "cases": {
            "case_a": {
                "milvus": {"exists": True, "person_ids": ["P01"], "is_graph_built": False},
                "neo4j": {"content_count": 0},
            }
        }
    }

    failures = assert_case_state(case, observed)

    assert failures == []


def test_assert_case_state_reports_person_id_mismatch():
    case = {
        "id": "case_a",
        "expect_state": {"milvus": {"exists": True, "person_ids": ["P01"]}},
    }
    observed = {
        "cases": {
            "case_a": {
                "milvus": {"exists": True, "person_ids": ["P02"]},
                "neo4j": {"content_count": 0},
            }
        }
    }

    failures = assert_case_state(case, observed)

    assert failures == [
        AssertionFailure(
            case_id="case_a",
            path="milvus.person_ids",
            expected=["P01"],
            observed=["P02"],
        )
    ]


def test_assert_case_state_checks_after_case_expectations():
    case = {
        "id": "case_c",
        "expect_state": {
            "after_case": {
                "case_a": {"milvus": {"is_graph_built": True}, "neo4j": {"content_count": 1}}
            }
        },
    }
    observed = {
        "cases": {
            "case_c": {"milvus": {"exists": False}, "neo4j": {"content_count": 1}},
            "case_a": {"milvus": {"is_graph_built": False}, "neo4j": {"content_count": 1}},
        }
    }

    failures = assert_case_state(case, observed)

    assert failures == [
        AssertionFailure(
            case_id="case_a",
            path="milvus.is_graph_built",
            expected=True,
            observed=False,
        )
    ]


class FakeMilvusInspector:
    def __init__(self):
        self.rows = {
            "case_a": {"exists": True, "person_ids": ["P01"], "is_graph_built": False},
            "case_b": {"exists": False, "person_ids": [], "is_graph_built": None},
        }

    async def inspect_case(self, case):
        return self.rows[case["id"]]


class FakeNeo4jInspector:
    def __init__(self):
        self.rows = {
            "case_a": {"content_count": 0, "duplicate_content": False},
            "case_b": {"content_count": 1, "duplicate_content": False},
        }

    async def inspect_case(self, case):
        return self.rows[case["id"]]


@pytest.mark.asyncio
async def test_collect_case_state_snapshot_uses_inspectors():
    cases = [
        {"id": "case_a", "text": "alpha", "event_id": "E001"},
        {"id": "case_b", "text": "beta", "event_id": "E002"},
    ]

    snapshot = await collect_case_state_snapshot(
        cases,
        milvus_inspector=FakeMilvusInspector(),
        neo4j_inspector=FakeNeo4jInspector(),
    )

    assert snapshot == {
        "cases": {
            "case_a": {
                "milvus": {"exists": True, "person_ids": ["P01"], "is_graph_built": False},
                "neo4j": {"content_count": 0, "duplicate_content": False},
            },
            "case_b": {
                "milvus": {"exists": False, "person_ids": [], "is_graph_built": None},
                "neo4j": {"content_count": 1, "duplicate_content": False},
            },
        }
    }


class FakeMilvusStore:
    def __init__(self, rows):
        self.rows = rows
        self.filters = []

    def _quote_literal(self, value):
        return f'"{value}"'

    def _query_rows(self, filter_expr, output_fields):
        del output_fields
        self.filters.append(filter_expr)
        return list(self.rows)


@pytest.mark.asyncio
async def test_milvus_case_inspector_queries_by_event_id():
    inspector = MilvusCaseInspector(
        store=FakeMilvusStore(
            [
                {
                    "event_id": "E001",
                    "person_ids": ["P01"],
                    "is_graph_built": False,
                },
            ]
        )
    )

    result = await inspector.inspect_case({"id": "case_x", "text": "alpha", "event_id": "E001"})

    assert result == {
        "exists": True,
        "person_ids": ["P01"],
        "is_graph_built": False,
        "event_id": "E001",
    }
    assert inspector._store.filters == ['event_id in ["E001"]']
