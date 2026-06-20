import csv
import json

import pytest
from PIL import Image

from sentinel_edge.evidence import charts
from sentinel_edge.evidence.charts import (
    CHART_HEIGHT,
    CHART_WIDTH,
    build_baseline_comparison_figure,
    build_case_latency_figure,
    build_hardware_timeseries_figure,
    render_html_to_png,
    write_case_latency_chart,
    write_figure_html,
)
from sentinel_edge.evidence.models import (
    CaseEvidence,
    EvidencePack,
    HardwareSample,
    MetricValue,
    Source,
)
from sentinel_edge.evidence.writer import write_evidence_pack


def test_write_evidence_pack_outputs_json_csv_and_directories(tmp_path):
    pack = EvidencePack(
        project="Sentinel Edge",
        generated_at="2026-06-19T10:00:00+08:00",
        pipeline_executed=True,
        hardware_profile={"gpu_detected": False},
        cases=[
            CaseEvidence(
                case_id="finance_01",
                title="Salary inflow anomaly",
                event_id="evt-001",
                status="completed",
                risk_level="high",
                risk_score=0.91,
                elapsed_ms=123.0,
                case_log_path="logs/finance_01.log",
            )
        ],
        hardware_samples=[
            HardwareSample(
                timestamp="2026-06-19T10:00:01+08:00",
                gpu_util_percent=MetricValue(42.0, "%", Source.MEASURED),
                vram_used_mb=MetricValue(2048.0, "MB", Source.MEASURED),
                power_watts=MetricValue.not_available("W", "sampler unavailable"),
                raw_output="GPU use: 42%",
            )
        ],
        ppt_metrics={"p13": {"case_count": {"value": 1}}},
    )

    root = write_evidence_pack(pack, tmp_path)

    assert root == tmp_path
    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["project"] == "Sentinel Edge"
    assert evidence["hardware_samples"][0]["power_watts"]["source"] == ("not_available")
    assert (
        json.loads((tmp_path / "ppt_metrics.json").read_text(encoding="utf-8"))["p13"][
            "case_count"
        ]["value"]
        == 1
    )

    case_rows = list(
        csv.DictReader((tmp_path / "case_results.csv").open(encoding="utf-8"))
    )
    assert case_rows[0] == {
        "case_id": "finance_01",
        "title": "Salary inflow anomaly",
        "event_id": "evt-001",
        "status": "completed",
        "risk_level": "high",
        "risk_score": "0.91",
        "elapsed_ms": "123.0",
        "error": "",
        "case_log_path": "logs/finance_01.log",
    }

    hardware_rows = list(
        csv.DictReader((tmp_path / "hardware_samples.csv").open(encoding="utf-8"))
    )
    assert hardware_rows[0] == {
        "timestamp": "2026-06-19T10:00:01+08:00",
        "gpu_util_percent": "42.0",
        "vram_used_mb": "2048.0",
        "power_watts": "",
        "raw_output": "GPU use: 42%",
    }
    assert (tmp_path / "stage_timings.csv").read_text(encoding="utf-8") == (
        "case_id,stage,elapsed_ms,source\n"
    )
    assert (tmp_path / "charts" / "html").is_dir()
    assert (tmp_path / "charts" / "png").is_dir()
    assert (tmp_path / "logs").is_dir()


def test_write_evidence_pack_serializes_metric_values_in_ppt_metrics(tmp_path):
    pack = EvidencePack(
        project="Sentinel Edge",
        generated_at="2026-06-19T10:00:00+08:00",
        pipeline_executed=False,
        hardware_profile={},
        ppt_metrics={
            "p13": {
                "case_count": MetricValue(1, "case", Source.DERIVED),
            },
        },
    )

    write_evidence_pack(pack, tmp_path)

    metrics = json.loads((tmp_path / "ppt_metrics.json").read_text(encoding="utf-8"))
    assert metrics["p13"]["case_count"] == {
        "value": 1,
        "unit": "case",
        "source": "derived",
        "note": "",
    }


def test_case_latency_figure_uses_horizontal_bars_sorted_by_elapsed_ms():
    fig = build_case_latency_figure(
        [
            CaseEvidence(case_id="failed", title="Failed", elapsed_ms=50.0, error="x"),
            CaseEvidence(case_id="finance_02", title="B", elapsed_ms=300.0),
            CaseEvidence(case_id="finance_01", title="A", elapsed_ms=100.0),
        ]
    )

    assert fig.data[0].orientation == "h"
    assert list(fig.data[0].y) == ["finance_01", "finance_02"]
    assert list(fig.data[0].x) == [0.1, 0.3]


def test_baseline_comparison_uses_plotly_table_for_mixed_units():
    fig = build_baseline_comparison_figure(
        {
            "p11": {
                "baseline": {
                    "pass_rate": {"value": 0.8, "unit": ""},
                    "risk_level_consistency": {"value": 0.75, "unit": ""},
                    "average_latency_ms": {"value": 2200, "unit": "ms"},
                    "average_power_watts": {"value": 70, "unit": "W"},
                },
                "optimized": {
                    "pass_rate": {"value": 0.95, "unit": ""},
                    "risk_level_consistency": {"value": 0.92, "unit": ""},
                    "average_latency_ms": {"value": 1200, "unit": "ms"},
                    "average_power_watts": {"value": 48, "unit": "W"},
                },
            }
        }
    )

    assert [trace.type for trace in fig.data] == ["table"]
    assert "Pass Rate" in fig.data[0].cells.values[0]
    assert "Risk Level Consistency" in fig.data[0].cells.values[0]
    assert "Average Latency" in fig.data[0].cells.values[0]
    assert "Average Power" in fig.data[0].cells.values[0]


def test_write_case_latency_chart_creates_self_contained_plotly_html(tmp_path):
    output = tmp_path / "case_latency.html"

    write_case_latency_chart(
        [CaseEvidence(case_id="finance_01", title="A", elapsed_ms=100.0)],
        output,
    )

    text = output.read_text(encoding="utf-8")
    assert "plotly" in text.lower()
    assert "<script src=" not in text
    assert "End-to-End Case Latency" in text


def test_write_figure_html_uses_stable_div_id_from_filename(tmp_path):
    output = tmp_path / "stable_case_latency.html"
    fig = build_case_latency_figure(
        [CaseEvidence(case_id="finance_01", title="A", elapsed_ms=100.0)]
    )

    write_figure_html(fig, output)
    first = output.read_text(encoding="utf-8")
    write_figure_html(fig, output)
    second = output.read_text(encoding="utf-8")

    assert first == second
    assert 'id="stable_case_latency"' in first


def test_write_case_latency_chart_render_png_uses_fixed_chart_size(tmp_path):
    html_path = tmp_path / "case_latency.html"
    png_path = tmp_path / "case_latency.png"

    write_case_latency_chart(
        [CaseEvidence(case_id="finance_01", title="A", elapsed_ms=100.0)],
        html_path,
        png_path,
        render_png=True,
    )

    with Image.open(png_path) as image:
        assert image.size == (CHART_WIDTH, CHART_HEIGHT)


def test_render_html_to_png_closes_browser_when_navigation_fails(
    tmp_path,
    monkeypatch,
):
    html_path = tmp_path / "chart.html"
    html_path.write_text("<html><body></body></html>", encoding="utf-8")
    png_path = tmp_path / "chart.png"
    fake_browser = _FakeBrowser()

    def fake_sync_playwright():
        return _FakePlaywright(fake_browser)

    monkeypatch.setattr(charts, "sync_playwright", fake_sync_playwright)

    with pytest.raises(RuntimeError, match="navigation failed"):
        render_html_to_png(html_path, png_path)

    assert fake_browser.closed is True


def test_hardware_timeseries_uses_separate_y_axes_for_mixed_units():
    fig = build_hardware_timeseries_figure(
        [
            HardwareSample(
                timestamp="2026-06-19T10:00:00+08:00",
                gpu_util_percent=MetricValue(10.0, "%", Source.MEASURED),
                vram_used_mb=MetricValue(1024.0, "MB", Source.MEASURED),
                power_watts=MetricValue(44.0, "W", Source.MEASURED),
            ),
            HardwareSample(
                timestamp="2026-06-19T10:00:01+08:00",
                gpu_util_percent=MetricValue(50.0, "%", Source.MEASURED),
                vram_used_mb=MetricValue(3072.0, "MB", Source.MEASURED),
                power_watts=MetricValue(58.0, "W", Source.MEASURED),
            ),
        ]
    )

    assert [trace.yaxis for trace in fig.data] == ["y", "y2", "y3"]
    assert fig.layout.yaxis.title.text == "GPU Utilization (%)"
    assert fig.layout.yaxis2.title.text == "VRAM Used (MB)"
    assert fig.layout.yaxis3.title.text == "Power (W)"


def test_empty_latency_chart_has_explicit_unavailable_annotation():
    fig = build_case_latency_figure([])

    assert fig.layout.annotations
    assert "No successful case timings available" in fig.layout.annotations[0].text
    assert fig.layout.xaxis.visible is False
    assert fig.layout.yaxis.visible is False


class _FakePlaywright:
    def __init__(self, browser):
        self.chromium = _FakeChromium(browser)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeChromium:
    def __init__(self, browser):
        self._browser = browser

    def launch(self, *, headless):
        assert headless is True
        return self._browser


class _FakeBrowser:
    def __init__(self):
        self.closed = False

    def new_page(self, *, viewport):
        assert viewport == {"width": CHART_WIDTH, "height": CHART_HEIGHT}
        return _FakePage()

    def close(self):
        self.closed = True


class _FakePage:
    def goto(self, *_args, **_kwargs):
        raise RuntimeError("navigation failed")
