from datetime import datetime

import pytest

from sentinel_edge.evidence.models import MetricValue, Source
from sentinel_edge.evidence.sidecar import load_sidecar, merge_metric


def test_load_sidecar_reads_yaml_mapping_with_meta(tmp_path):
    sidecar_path = tmp_path / "evidence.yaml"
    sidecar_path.write_text(
        """
p10:
  ttft_ms:
    value: 18.5
    note: llama.cpp smoke run
""".lstrip(),
        encoding="utf-8",
    )

    sidecar = load_sidecar(sidecar_path)

    assert sidecar["p10"]["ttft_ms"]["value"] == 18.5
    assert sidecar["_meta"]["path"] == str(sidecar_path)
    datetime.fromisoformat(sidecar["_meta"]["loaded_at"])


def test_load_sidecar_rejects_non_mapping_yaml(tmp_path):
    sidecar_path = tmp_path / "evidence.yaml"
    sidecar_path.write_text("- p10\n- p11\n", encoding="utf-8")

    with pytest.raises(ValueError, match="must contain a mapping"):
        load_sidecar(sidecar_path)


def test_load_sidecar_reads_json_mapping_with_meta(tmp_path):
    sidecar_path = tmp_path / "evidence.json"
    sidecar_path.write_text(
        '{"p10": {"tokens_per_second": {"value": 22.0}}}',
        encoding="utf-8",
    )

    sidecar = load_sidecar(sidecar_path)

    assert sidecar["p10"]["tokens_per_second"]["value"] == 22.0
    assert sidecar["_meta"]["path"] == str(sidecar_path)


def test_load_sidecar_returns_empty_mapping_for_none_and_empty_file(tmp_path):
    sidecar_path = tmp_path / "empty.yaml"
    sidecar_path.write_text("", encoding="utf-8")

    assert load_sidecar(None) == {}
    assert load_sidecar(sidecar_path) == {}


def test_load_sidecar_raises_file_not_found_with_path(tmp_path):
    missing_path = tmp_path / "missing.yaml"

    with pytest.raises(FileNotFoundError, match=str(missing_path)):
        load_sidecar(missing_path)


def test_load_sidecar_wraps_malformed_json_with_path(tmp_path):
    sidecar_path = tmp_path / "broken.json"
    sidecar_path.write_text('{"p10": ', encoding="utf-8")

    with pytest.raises(ValueError, match="could not be parsed") as exc_info:
        load_sidecar(sidecar_path)

    assert str(sidecar_path) in str(exc_info.value)


def test_merge_metric_prefers_measured_metric_without_override():
    measured = MetricValue(value=42.0, unit="W", source=Source.MEASURED)

    merged = merge_metric(measured, {"value": 90.0, "note": "manual fallback"})

    assert merged is measured


def test_merge_metric_fills_not_available_metric_from_sidecar():
    measured = MetricValue.not_available("ms", "sampler missing")

    merged = merge_metric(
        measured,
        {"value": 18.5, "note": "llama.cpp smoke run"},
        unit="ms",
    )

    assert merged == MetricValue(
        value=18.5,
        unit="ms",
        source=Source.SIDECAR,
        note="llama.cpp smoke run",
    )


def test_merge_metric_accepts_non_dict_sidecar_value():
    measured = MetricValue.not_available("tokens/s")

    merged = merge_metric(measured, 22.0)

    assert merged == MetricValue(
        value=22.0,
        unit="tokens/s",
        source=Source.SIDECAR,
        note="",
    )


def test_merge_metric_allows_explicit_sidecar_override():
    measured = MetricValue(value=50.0, unit="W", source=Source.DERIVED)

    merged = merge_metric(
        measured,
        {"value": 47.5, "note": "external meter", "override": True},
    )

    assert merged == MetricValue(
        value=47.5,
        unit="W",
        source=Source.SIDECAR,
        note="external meter",
    )


def test_merge_metric_rejects_non_boolean_override():
    measured = MetricValue(value=50.0, unit="W", source=Source.DERIVED)

    with pytest.raises(ValueError, match="override must be a boolean"):
        merge_metric(
            measured,
            {"value": 47.5, "note": "manual fallback", "override": "false"},
        )


def test_merge_metric_keeps_measured_metric_when_sidecar_value_is_null():
    measured = MetricValue(value=50.0, unit="W", source=Source.DERIVED)

    merged = merge_metric(
        measured,
        {"value": None, "note": "fill after measurement"},
        unit="W",
    )

    assert merged is measured


def test_merge_metric_keeps_not_available_when_sidecar_value_is_null():
    measured = MetricValue.not_available("ms", "sampler missing")

    merged = merge_metric(
        measured,
        {"value": None, "note": "fill after measurement"},
        unit="ms",
    )

    assert merged.value is None
    assert merged.unit == "ms"
    assert merged.source is Source.NOT_AVAILABLE
    assert "sidecar value is null" in merged.note
    assert "fill after measurement" in merged.note
