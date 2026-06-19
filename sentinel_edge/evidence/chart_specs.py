"""Chart selection metadata for PPT evidence slides."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChartSpec:
    key: str
    chart_type: str
    data_properties: tuple[str, ...]
    why_not_default_bar: str
    fallback_chart_type: str = "empty_state"
    render_requirements: tuple[str, ...] = ()


CHART_SPECS: dict[str, ChartSpec] = {
    "case_latency": ChartSpec(
        key="case_latency",
        chart_type="sorted_horizontal_bar",
        data_properties=(
            "case-level elapsed_ms measurements",
            "case identifiers and titles used as labels",
            "success/error status for annotation",
        ),
        why_not_default_bar=(
            "long labels and long-tailed latency need horizontal sorting plus "
            "mean and P95 context, not a default vertical bar chart."
        ),
        render_requirements=(
            "sorted_by_elapsed_ms",
            "mean_reference_line",
            "p95_reference_line",
            "horizontal_labels",
        ),
    ),
    "stage_breakdown": ChartSpec(
        key="stage_breakdown",
        chart_type="stacked_horizontal_bar",
        data_properties=(
            "per-stage elapsed time contributions",
            "case identifiers used as rows",
            "measurement availability flags for missing stages",
        ),
        why_not_default_bar=(
            "A single bar hides which pipeline stage dominates each case."
        ),
        fallback_chart_type="measurement_availability",
        render_requirements=(
            "stacked_when_spans_exist",
            "measurement_availability_when_absent",
        ),
    ),
    "hardware_timeseries": ChartSpec(
        key="hardware_timeseries",
        chart_type="faceted_timeseries",
        data_properties=(
            "timestamped GPU utilization samples",
            "timestamped VRAM usage samples",
            "timestamped power draw samples",
        ),
        why_not_default_bar=(
            "Hardware telemetry is time-varying and uses mixed units that need "
            "separate aligned panels."
        ),
        render_requirements=(
            "facet_gpu_util_percent",
            "facet_vram_used_mb",
            "facet_power_watts",
            "shared_time_axis",
        ),
    ),
    "baseline_comparison": ChartSpec(
        key="baseline_comparison",
        chart_type="scorecard_table",
        data_properties=(
            "baseline metric values",
            "optimized metric values",
            "units, sources, and notes for each comparison point",
        ),
        why_not_default_bar=(
            "Baseline evidence mixes rates, latency, power, and qualitative "
            "status, which is clearer as paired scorecards."
        ),
        render_requirements=(
            "mixed_unit_table",
            "direction_column_or_delta",
            "no_grouped_unit_bar",
        ),
    ),
    "risk_consistency": ChartSpec(
        key="risk_consistency",
        chart_type="stacked_category_matrix",
        data_properties=(
            "risk level categories",
            "case or run identifiers",
            "consistency counts across repeated evaluations",
        ),
        why_not_default_bar=(
            "Risk stability is categorical and comparative, so a matrix shows "
            "agreement patterns more directly."
        ),
        render_requirements=(
            "expected_vs_observed_matrix",
            "stacked_category_matrix",
        ),
    ),
    "evidence_availability": ChartSpec(
        key="evidence_availability",
        chart_type="source_status_matrix",
        data_properties=(
            "metric source status values",
            "slide or evidence section identifiers",
            "availability notes for missing measurements",
        ),
        why_not_default_bar=(
            "Evidence readiness is a source/status grid rather than a numeric "
            "magnitude comparison."
        ),
        render_requirements=("source_status_matrix",),
    ),
}


def chart_spec_for(key: str) -> ChartSpec:
    return CHART_SPECS[key]
