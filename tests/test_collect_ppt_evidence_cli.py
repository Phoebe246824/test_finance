import argparse
import json
from dataclasses import dataclass

import pytest

from sentinel_edge.evidence.models import HardwareSample, MetricValue, Source


def test_parse_args_accepts_sidecar_case_and_sample_interval():
    from scripts.collect_ppt_evidence import parse_args

    args = parse_args(
        [
            "--case",
            "finance_04_aml_high_risk_recall",
            "--sidecar",
            "docs/competition/evidence_sidecar.example.yaml",
            "--sample-interval",
            "2.5",
        ]
    )

    assert args.case == ["finance_04_aml_high_risk_recall"]
    assert args.sidecar == "docs/competition/evidence_sidecar.example.yaml"
    assert args.sample_interval == 2.5


def test_build_output_dir_uses_explicit_path(tmp_path):
    from scripts.collect_ppt_evidence import build_output_dir

    output = build_output_dir(str(tmp_path / "manual"))

    assert output == tmp_path / "manual"


@pytest.mark.asyncio
async def test_main_async_without_run_pipeline_writes_pack_and_skips_pipeline(
    tmp_path,
    monkeypatch,
    capsys,
):
    import scripts.collect_ppt_evidence as cli

    pipeline_called = False

    async def fake_run_cases(*_args, **_kwargs):
        nonlocal pipeline_called
        pipeline_called = True
        return []

    monkeypatch.setattr(cli, "load_sidecar", lambda path: {"sidecar_path": path})
    monkeypatch.setattr(cli, "collect_hardware_profile", lambda: _FakeProfile())
    monkeypatch.setattr(
        cli,
        "sample_once",
        lambda: HardwareSample(
            timestamp="2026-06-20T10:00:00",
            gpu_util_percent=MetricValue(12.0, "%", Source.MEASURED),
        ),
    )
    monkeypatch.setattr(cli, "run_cases", fake_run_cases)
    _patch_chart_writers(monkeypatch, cli)

    args = argparse.Namespace(
        run_pipeline=False,
        case=["finance_04_aml_high_risk_recall"],
        sidecar="manual.yaml",
        sample_interval=0.1,
        output_dir=str(tmp_path),
    )

    output_dir = await cli.main_async(args)

    assert output_dir == tmp_path
    assert pipeline_called is False

    evidence = json.loads((tmp_path / "evidence.json").read_text(encoding="utf-8"))
    assert evidence["project"] == "Sentinel Edge"
    assert evidence["pipeline_executed"] is False
    assert evidence["cases"] == []
    assert evidence["hardware_profile"] == {"gpu_detected": False}
    assert evidence["sidecar"] == {"sidecar_path": "manual.yaml"}

    assert (tmp_path / "ppt_metrics.json").is_file()
    assert (tmp_path / "case_results.csv").is_file()
    assert (tmp_path / "hardware_samples.csv").is_file()
    assert (tmp_path / "stage_timings.csv").is_file()
    assert sorted(
        path.name for path in (tmp_path / "charts" / "html").glob("*.html")
    ) == [
        "baseline_comparison.html",
        "case_latency.html",
        "hardware_timeseries.html",
        "stage_breakdown.html",
    ]
    assert sorted(
        path.name for path in (tmp_path / "charts" / "png").glob("*.png")
    ) == [
        "baseline_comparison.png",
        "case_latency.png",
        "hardware_timeseries.png",
        "stage_breakdown.png",
    ]
    assert not (tmp_path / "chart_render_errors.json").exists()
    assert json.loads(capsys.readouterr().out)["output_dir"] == str(tmp_path)


@pytest.mark.asyncio
async def test_main_async_records_chart_render_errors_without_failing(
    tmp_path,
    monkeypatch,
):
    import scripts.collect_ppt_evidence as cli

    monkeypatch.setattr(cli, "load_sidecar", lambda _path: {})
    monkeypatch.setattr(cli, "collect_hardware_profile", lambda: _FakeProfile())
    monkeypatch.setattr(
        cli,
        "sample_once",
        lambda: HardwareSample(timestamp="2026-06-20T10:00:00"),
    )
    _patch_chart_writers(monkeypatch, cli, fail_key="case_latency")

    args = argparse.Namespace(
        run_pipeline=False,
        case=None,
        sidecar=None,
        sample_interval=1.0,
        output_dir=str(tmp_path),
    )

    output_dir = await cli.main_async(args)

    assert output_dir == tmp_path
    assert (tmp_path / "charts" / "html" / "case_latency.html").is_file()
    assert not (tmp_path / "charts" / "png" / "case_latency.png").exists()
    assert (tmp_path / "charts" / "png" / "stage_breakdown.png").is_file()

    errors = json.loads(
        (tmp_path / "chart_render_errors.json").read_text(encoding="utf-8")
    )
    assert errors == [
        {
            "chart": "case_latency",
            "error": "RuntimeError: chromium unavailable",
        }
    ]


@dataclass
class _FakeProfile:
    def to_dict(self) -> dict[str, bool]:
        return {"gpu_detected": False}


def _patch_chart_writers(monkeypatch, cli, *, fail_key: str | None = None) -> None:
    def make_writer(key: str):
        def writer(_data, html_path, png_path, *, render_png):
            assert render_png is True
            html_path.write_text(f"<html>{key}</html>", encoding="utf-8")
            if key == fail_key:
                raise RuntimeError("chromium unavailable")
            png_path.write_bytes(b"png")
            return html_path

        return writer

    monkeypatch.setattr(cli, "write_case_latency_chart", make_writer("case_latency"))
    monkeypatch.setattr(
        cli,
        "write_stage_breakdown_chart",
        make_writer("stage_breakdown"),
    )
    monkeypatch.setattr(
        cli,
        "write_hardware_timeseries_chart",
        make_writer("hardware_timeseries"),
    )
    monkeypatch.setattr(
        cli,
        "write_baseline_comparison_chart",
        make_writer("baseline_comparison"),
    )
