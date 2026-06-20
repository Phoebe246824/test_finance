"""Plotly chart builders for PPT evidence artifacts."""

from __future__ import annotations

from pathlib import Path
import re
from statistics import mean
from time import sleep
from typing import Any

import plotly.graph_objects as go
from plotly.subplots import make_subplots
from playwright.sync_api import sync_playwright

from sentinel_edge.evidence.aggregator import percentile
from sentinel_edge.evidence.models import CaseEvidence, HardwareSample

CHART_WIDTH = 1600
CHART_HEIGHT = 900

_TITLE_COLOR = "#172033"
_BODY_COLOR = "#354052"
_MUTED_COLOR = "#667085"
_BLUE = "#2F6FED"
_GREEN = "#00A676"
_ORANGE = "#E07A5F"
_PURPLE = "#7B2CBF"


def _apply_theme(fig: go.Figure, title: str) -> go.Figure:
    fig.update_layout(
        title={"text": title, "x": 0.03, "xanchor": "left", "font": {"size": 34}},
        template="plotly_white",
        width=CHART_WIDTH,
        height=CHART_HEIGHT,
        margin={"l": 150, "r": 90, "t": 115, "b": 95},
        font={
            "family": "Noto Sans CJK SC, Microsoft YaHei, Arial, sans-serif",
            "size": 22,
            "color": _BODY_COLOR,
        },
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        hovermode="closest",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
    )
    fig.update_xaxes(
        showgrid=True,
        gridcolor="#E5E7EB",
        zeroline=False,
        linecolor="#D0D5DD",
        tickfont={"size": 18},
        title_font={"size": 20},
    )
    fig.update_yaxes(
        showgrid=False,
        linecolor="#D0D5DD",
        tickfont={"size": 18},
        title_font={"size": 20},
    )
    return fig


def empty_state_figure(title: str, message: str) -> go.Figure:
    """Return a themed empty-state chart with an explicit annotation."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        align="center",
        font={"size": 30, "color": _MUTED_COLOR},
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return _apply_theme(fig, title)


def build_case_latency_figure(cases: list[CaseEvidence]) -> go.Figure:
    """Build a sorted horizontal case-latency chart."""
    measured = [
        case for case in cases if case.succeeded and case.elapsed_ms is not None
    ]
    if not measured:
        return empty_state_figure(
            "End-to-End Case Latency",
            "No successful case timings available",
        )

    measured.sort(key=lambda case: float(case.elapsed_ms or 0))
    labels = [case.case_id for case in measured]
    seconds = [round(float(case.elapsed_ms or 0) / 1000, 3) for case in measured]
    average_seconds = round(mean(seconds), 3)
    p95_seconds = percentile(seconds, 95)

    fig = go.Figure()
    fig.add_bar(
        x=seconds,
        y=labels,
        orientation="h",
        marker={"color": _BLUE},
        name="Case latency",
        customdata=[case.title for case in measured],
        hovertemplate="%{y}<br>%{customdata}<br>%{x:.3f}s<extra></extra>",
    )
    fig.add_vline(
        x=average_seconds,
        line_dash="dash",
        line_color=_ORANGE,
        annotation_text=f"mean {average_seconds:.2f}s",
        annotation_position="top",
    )
    if p95_seconds is not None:
        fig.add_vline(
            x=p95_seconds,
            line_dash="dot",
            line_color=_PURPLE,
            annotation_text=f"P95 {p95_seconds:.2f}s",
            annotation_position="top",
        )
    fig.update_xaxes(title_text="Seconds")
    fig.update_yaxes(title_text="", automargin=True)
    return _apply_theme(fig, "End-to-End Case Latency")


def build_stage_breakdown_figure(stage_rows: list[dict[str, Any]]) -> go.Figure:
    """Build a stacked horizontal breakdown when stage spans are available."""
    if not stage_rows:
        return empty_state_figure(
            "Pipeline Stage Breakdown",
            "Detailed stage timings unavailable for this run",
        )

    case_ids = sorted({str(row.get("case_id", "")) for row in stage_rows})
    stages = sorted({str(row.get("stage", "")) for row in stage_rows})
    fig = go.Figure()
    for stage in stages:
        values = [
            _stage_seconds(stage_rows, case_id=case_id, stage=stage)
            for case_id in case_ids
        ]
        fig.add_bar(y=case_ids, x=values, name=stage, orientation="h")

    fig.update_layout(barmode="stack")
    fig.update_xaxes(title_text="Seconds")
    fig.update_yaxes(title_text="", automargin=True)
    return _apply_theme(fig, "Pipeline Stage Breakdown")


def build_hardware_timeseries_figure(samples: list[HardwareSample]) -> go.Figure:
    """Build small-multiple hardware telemetry charts with separate y-axes."""
    measured = [sample for sample in samples if sample.timestamp]
    if not measured:
        return empty_state_figure(
            "Hardware Runtime Samples",
            "No runtime hardware samples available",
        )

    timestamps = [sample.timestamp for sample in measured]
    series = [
        (
            "GPU Utilization (%)",
            [sample.gpu_util_percent.value for sample in measured],
            _BLUE,
        ),
        (
            "VRAM Used (MB)",
            [sample.vram_used_mb.value for sample in measured],
            _GREEN,
        ),
        (
            "Power (W)",
            [sample.power_watts.value for sample in measured],
            _ORANGE,
        ),
    ]
    if not any(any(value is not None for value in values) for _, values, _ in series):
        return empty_state_figure(
            "Hardware Runtime Samples",
            "GPU, VRAM, and power samples are unavailable",
        )

    fig = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=[name for name, _, _ in series],
    )
    for row_index, (name, values, color) in enumerate(series, start=1):
        fig.add_scatter(
            x=timestamps,
            y=values,
            mode="lines+markers",
            name=name,
            line={"color": color, "width": 3},
            marker={"size": 8},
            connectgaps=False,
            row=row_index,
            col=1,
        )
        fig.update_yaxes(title_text=name, row=row_index, col=1)

    fig.update_xaxes(title_text="Time", row=3, col=1)
    fig.update_layout(showlegend=False)
    return _apply_theme(fig, "Hardware Runtime Samples")


def build_baseline_comparison_figure(ppt_metrics: dict[str, Any]) -> go.Figure:
    """Build a mixed-unit baseline comparison as a Plotly table."""
    p11 = ppt_metrics.get("p11", {})
    baseline = _metric_group(p11.get("baseline"))
    optimized = _metric_group(p11.get("optimized"))
    rows = [
        (
            "Pass Rate",
            baseline.get("pass_rate"),
            optimized.get("pass_rate"),
            "Higher is better",
        ),
        (
            "Risk Level Consistency",
            baseline.get("risk_level_consistency"),
            optimized.get("risk_level_consistency"),
            "Higher is better",
        ),
        (
            "Average Latency",
            baseline.get("average_latency_ms"),
            optimized.get("average_latency_ms"),
            "Lower is better",
        ),
        (
            "Average Power",
            baseline.get("average_power_watts"),
            optimized.get("average_power_watts"),
            "Lower is better",
        ),
    ]

    fig = go.Figure(
        data=[
            go.Table(
                columnwidth=[0.28, 0.24, 0.24, 0.24],
                header={
                    "values": ["Metric", "Baseline", "Optimized", "Direction"],
                    "fill_color": _TITLE_COLOR,
                    "font": {"color": "#ffffff", "size": 24},
                    "align": "left",
                    "height": 46,
                },
                cells={
                    "values": [
                        [row[0] for row in rows],
                        [_metric_text(row[1]) for row in rows],
                        [_metric_text(row[2]) for row in rows],
                        [row[3] for row in rows],
                    ],
                    "fill_color": "#F8FAFC",
                    "font": {"color": _BODY_COLOR, "size": 22},
                    "align": "left",
                    "height": 54,
                },
            )
        ]
    )
    return _apply_theme(fig, "Baseline vs Local Optimized Model")


def write_figure_html(
    fig: go.Figure,
    output_path: str | Path,
    *,
    div_id: str | None = None,
) -> Path:
    """Write a self-contained Plotly HTML file."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    plot_html = fig.to_html(
        full_html=False,
        include_plotlyjs=True,
        config={"displayModeBar": False, "responsive": False},
        div_id=div_id or _stable_div_id(output),
    )
    output.write_text(
        _wrap_chart_html(plot_html),
        encoding="utf-8",
    )
    return output


def render_html_to_png(html_path: str | Path, png_path: str | Path) -> Path:
    """Render a chart HTML file to PNG with headless Chromium."""
    source = Path(html_path).resolve()
    output = Path(png_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                viewport={"width": CHART_WIDTH, "height": CHART_HEIGHT}
            )
            page.goto(source.as_uri(), wait_until="domcontentloaded")
            page.locator(".plotly-graph-div").wait_for(timeout=10_000)
            sleep(0.2)
            page.screenshot(path=output, full_page=False)
        finally:
            browser.close()
    return output


def write_case_latency_chart(
    cases: list[CaseEvidence],
    html_path: str | Path,
    png_path: str | Path | None = None,
    *,
    render_png: bool = False,
) -> Path:
    html = write_figure_html(build_case_latency_figure(cases), html_path)
    if render_png and png_path is not None:
        render_html_to_png(html, png_path)
    return html


def write_stage_breakdown_chart(
    stage_rows: list[dict[str, Any]],
    html_path: str | Path,
    png_path: str | Path | None = None,
    *,
    render_png: bool = False,
) -> Path:
    html = write_figure_html(build_stage_breakdown_figure(stage_rows), html_path)
    if render_png and png_path is not None:
        render_html_to_png(html, png_path)
    return html


def write_hardware_timeseries_chart(
    samples: list[HardwareSample],
    html_path: str | Path,
    png_path: str | Path | None = None,
    *,
    render_png: bool = False,
) -> Path:
    html = write_figure_html(build_hardware_timeseries_figure(samples), html_path)
    if render_png and png_path is not None:
        render_html_to_png(html, png_path)
    return html


def write_baseline_comparison_chart(
    ppt_metrics: dict[str, Any],
    html_path: str | Path,
    png_path: str | Path | None = None,
    *,
    render_png: bool = False,
) -> Path:
    html = write_figure_html(build_baseline_comparison_figure(ppt_metrics), html_path)
    if render_png and png_path is not None:
        render_html_to_png(html, png_path)
    return html


def _stage_seconds(
    stage_rows: list[dict[str, Any]],
    *,
    case_id: str,
    stage: str,
) -> float:
    for row in stage_rows:
        if (
            str(row.get("case_id", "")) == case_id
            and str(row.get("stage", "")) == stage
        ):
            return float(row.get("elapsed_ms") or 0) / 1000
    return 0.0


def _metric_group(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _metric_text(metric: Any) -> str:
    if not isinstance(metric, dict):
        return "not_available"

    value = metric.get("value")
    unit = metric.get("unit", "")
    source = metric.get("source", "")
    if value is None:
        return f"not_available ({source})" if source else "not_available"

    suffix = f" {unit}" if unit else ""
    source_suffix = f" ({source})" if source else ""
    return f"{value}{suffix}{source_suffix}"


def _stable_div_id(output: Path) -> str:
    div_id = re.sub(r"[^A-Za-z0-9_-]+", "_", output.stem).strip("_")
    return div_id or "chart"


def _wrap_chart_html(plot_html: str) -> str:
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <style>
    html,
    body {{
      margin: 0;
      padding: 0;
      width: {CHART_WIDTH}px;
      height: {CHART_HEIGHT}px;
      overflow: hidden;
      background: #ffffff;
    }}
  </style>
</head>
<body>
{plot_html}
</body>
</html>
"""
