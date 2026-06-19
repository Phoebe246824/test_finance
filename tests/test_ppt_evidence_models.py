from sentinel_edge.evidence import (
    CaseEvidence,
    HardwareSample,
    MetricValue,
    Source,
    to_plain_data,
)


def test_metric_value_serializes_source_to_plain_value():
    metric = MetricValue(
        value=123.4,
        unit="ms",
        source=Source.MEASURED,
        note="case run",
    )

    assert to_plain_data(metric) == {
        "value": 123.4,
        "unit": "ms",
        "source": "measured",
        "note": "case run",
    }


def test_case_evidence_succeeded_reflects_error_presence():
    assert CaseEvidence(case_id="case-1", title="Normal case").succeeded is True
    assert (
        CaseEvidence(
            case_id="case-2",
            title="Failed case",
            error="pipeline failed",
        ).succeeded
        is False
    )


def test_hardware_sample_serializes_not_available_metric():
    sample = HardwareSample(
        timestamp="2026-06-19T10:00:00+08:00",
        gpu_util_percent=MetricValue.not_available("%", "rocm-smi not found"),
    )

    data = to_plain_data(sample)

    assert data["gpu_util_percent"] == {
        "value": None,
        "unit": "%",
        "source": "not_available",
        "note": "rocm-smi not found",
    }
