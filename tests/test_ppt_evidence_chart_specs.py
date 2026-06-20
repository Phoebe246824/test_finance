from importlib import import_module

import pytest


def _chart_specs_module():
    try:
        return import_module("sentinel_edge.evidence.chart_specs")
    except ModuleNotFoundError as exc:
        if exc.name == "sentinel_edge.evidence.chart_specs":
            pytest.fail("sentinel_edge.evidence.chart_specs module should exist")
        raise


def test_case_latency_uses_sorted_horizontal_bar():
    chart_specs = _chart_specs_module()

    assert chart_specs.chart_spec_for("case_latency").chart_type == (
        "sorted_horizontal_bar"
    )


def test_stage_breakdown_falls_back_to_measurement_availability():
    chart_specs = _chart_specs_module()

    assert chart_specs.chart_spec_for("stage_breakdown").fallback_chart_type == (
        "measurement_availability"
    )


def test_hardware_timeseries_uses_faceted_timeseries():
    chart_specs = _chart_specs_module()

    assert chart_specs.chart_spec_for("hardware_timeseries").chart_type == (
        "faceted_timeseries"
    )


def test_baseline_comparison_uses_scorecard_table():
    chart_specs = _chart_specs_module()

    assert chart_specs.chart_spec_for("baseline_comparison").chart_type == (
        "scorecard_table"
    )


def test_every_chart_spec_documents_data_shape_and_bar_chart_decision():
    chart_specs = _chart_specs_module()

    assert chart_specs.CHART_SPECS
    for spec in chart_specs.CHART_SPECS.values():
        assert spec.chart_type
        assert spec.data_properties
        assert spec.why_not_default_bar


def test_chart_specs_cover_required_ppt_evidence_views():
    chart_specs = _chart_specs_module()

    assert set(chart_specs.CHART_SPECS) == {
        "baseline_comparison",
        "case_latency",
        "evidence_availability",
        "hardware_timeseries",
        "risk_consistency",
        "stage_breakdown",
    }


def test_case_latency_render_requirements_include_sort_and_reference_context():
    chart_specs = _chart_specs_module()

    spec = chart_specs.chart_spec_for("case_latency")

    assert {
        "sorted_by_elapsed_ms",
        "mean_reference_line",
        "p95_reference_line",
        "horizontal_labels",
    } <= set(spec.render_requirements)


def test_case_latency_rationale_mentions_label_shape_and_reference_context():
    chart_specs = _chart_specs_module()

    rationale = chart_specs.chart_spec_for("case_latency").why_not_default_bar

    assert "long labels" in rationale
    assert "long-tailed latency" in rationale
    assert "mean" in rationale
    assert "P95" in rationale


def test_hardware_timeseries_render_requirements_pin_facets_and_axis():
    chart_specs = _chart_specs_module()

    assert {
        "facet_gpu_util_percent",
        "facet_vram_used_mb",
        "facet_power_watts",
        "shared_time_axis",
    } <= set(chart_specs.chart_spec_for("hardware_timeseries").render_requirements)


def test_baseline_comparison_render_requirements_keep_mixed_units_tabular():
    chart_specs = _chart_specs_module()

    assert {
        "mixed_unit_table",
        "direction_column_or_delta",
        "no_grouped_unit_bar",
    } <= set(chart_specs.chart_spec_for("baseline_comparison").render_requirements)
