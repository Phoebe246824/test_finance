import pytest

from sentinel_edge.evidence.aggregator import build_ppt_metrics, percentile
from sentinel_edge.evidence.models import CaseEvidence, HardwareSample, MetricValue, Source


def test_percentile_uses_nearest_rank():
    assert percentile([100, 200, 300, 400], 95) == 400.0
    assert percentile([100, 200, 300, 400], 50) == 200.0
    assert percentile([], 95) is None


def test_build_ppt_metrics_summarizes_cases_and_hardware():
    cases = [
        CaseEvidence(case_id='case-1', title='Fast pass', elapsed_ms=100),
        CaseEvidence(case_id='case-2', title='Slow pass', elapsed_ms=300),
        CaseEvidence(
            case_id='case-3',
            title='Failed case',
            elapsed_ms=900,
            error='pipeline failed',
        ),
    ]
    hardware_samples = [
        HardwareSample(
            timestamp='2026-06-19T10:00:00+08:00',
            gpu_util_percent=MetricValue(12.0, '%', Source.MEASURED),
            vram_used_mb=MetricValue(4096, 'MB', Source.MEASURED),
            power_watts=MetricValue(55.5, 'W', Source.MEASURED),
        ),
        HardwareSample(
            timestamp='2026-06-19T10:00:01+08:00',
            gpu_util_percent=MetricValue.not_available('%', 'sampler skipped'),
            vram_used_mb=MetricValue.not_available('MB', 'sampler skipped'),
            power_watts=MetricValue.not_available('W', 'sampler skipped'),
        ),
    ]

    metrics = build_ppt_metrics(
        cases=cases,
        hardware_samples=hardware_samples,
        sidecar={},
    )

    assert {'p5', 'p8', 'p10', 'p11', 'p12', 'p13', 'p14'} <= metrics.keys()
    assert metrics['p10']['end_to_end_latency_mean_ms']['value'] == 200.0
    assert metrics['p10']['end_to_end_latency_mean_ms']['source'] == 'derived'
    assert metrics['p10']['end_to_end_latency_p95_ms']['value'] == 300.0
    assert metrics['p10']['gpu_peak_util_percent']['value'] == 12.0
    assert metrics['p10']['vram_peak_used_mb']['value'] == 4096
    assert metrics['p11']['optimized']['pass_rate']['value'] == pytest.approx(2 / 3)
    assert metrics['p8']['gpu_peak_util_percent'] is not (
        metrics['p10']['gpu_peak_util_percent']
    )
    assert metrics['p10']['average_power_watts'] is not (
        metrics['p11']['optimized']['average_power_watts']
    )
    assert metrics['p13']['case_count']['value'] == 3
    assert metrics['p13']['failed_case_count']['value'] == 1


def test_build_ppt_metrics_marks_missing_runtime_values():
    metrics = build_ppt_metrics(cases=[], hardware_samples=[], sidecar={})

    assert metrics['p10']['end_to_end_latency_mean_ms']['source'] == 'not_available'
    assert metrics['p10']['ttft_ms']['source'] == 'not_available'
    assert metrics['p11']['baseline']['average_power_watts']['source'] == (
        'not_available'
    )


def test_build_ppt_metrics_marks_null_sidecar_values_not_available():
    metrics = build_ppt_metrics(
        cases=[],
        hardware_samples=[],
        sidecar={
            'p10': {
                'ttft_ms': {'value': None, 'note': 'fill later'},
                'tokens_per_second': None,
            },
        },
    )

    ttft = metrics['p10']['ttft_ms']
    tokens_per_second = metrics['p10']['tokens_per_second']

    assert ttft['source'] == 'not_available'
    assert ttft['value'] is None
    assert 'p10.ttft_ms' in ttft['note']
    assert 'fill later' in ttft['note']
    assert tokens_per_second['source'] == 'not_available'
    assert tokens_per_second['value'] is None
    assert 'p10.tokens_per_second' in tokens_per_second['note']


def test_build_ppt_metrics_preserves_non_null_sidecar_values():
    metrics = build_ppt_metrics(
        cases=[],
        hardware_samples=[],
        sidecar={
            'p10': {
                'ttft_ms': {
                    'value': 18.5,
                    'unit': 'ms',
                    'note': 'llama.cpp smoke run',
                },
                'tokens_per_second': 22.0,
            },
        },
    )

    assert metrics['p10']['ttft_ms'] == {
        'value': 18.5,
        'unit': 'ms',
        'source': 'sidecar',
        'note': 'llama.cpp smoke run',
    }
    assert metrics['p10']['tokens_per_second'] == {
        'value': 22.0,
        'unit': 'tokens/s',
        'source': 'sidecar',
        'note': '',
    }


def test_build_ppt_metrics_uses_planned_sidecar_contract_keys():
    metrics = build_ppt_metrics(
        cases=[],
        hardware_samples=[],
        sidecar={
            'p10': {
                'average_power_watts': {
                    'value': 47.5,
                    'note': 'external meter',
                },
            },
            'p11': {
                'baseline': {
                    'pass_rate': {
                        'value': 0.75,
                        'note': 'baseline replay',
                    },
                },
                'optimized': {
                    'risk_level_consistency': {
                        'value': 0.9,
                        'note': 'repeated-run consistency',
                    },
                },
            },
            'p12': {
                'privacy_evidence': {
                    'value': 'docs/screenshots/privacy-log-masking.png',
                    'note': 'privacy screenshot',
                },
            },
            'p14': {
                'business_value': {
                    'value': 'docs/business-value.md',
                    'note': 'pilot material',
                },
            },
        },
    )

    assert metrics['p10']['average_power_watts'] == {
        'value': 47.5,
        'unit': 'W',
        'source': 'sidecar',
        'note': 'external meter',
    }
    assert metrics['p11']['baseline']['pass_rate'] == {
        'value': 0.75,
        'unit': '',
        'source': 'sidecar',
        'note': 'baseline replay',
    }
    assert metrics['p11']['optimized']['risk_level_consistency'] == {
        'value': 0.9,
        'unit': '',
        'source': 'sidecar',
        'note': 'repeated-run consistency',
    }
    assert metrics['p12']['privacy_evidence'] == {
        'value': 'docs/screenshots/privacy-log-masking.png',
        'unit': '',
        'source': 'sidecar',
        'note': 'privacy screenshot',
    }
    assert metrics['p14']['business_value'] == {
        'value': 'docs/business-value.md',
        'unit': '',
        'source': 'sidecar',
        'note': 'pilot material',
    }


def test_build_ppt_metrics_prefers_measured_power_average_over_sidecar():
    metrics = build_ppt_metrics(
        cases=[],
        hardware_samples=[
            HardwareSample(
                timestamp='2026-06-19T10:00:00+08:00',
                power_watts=MetricValue(40.0, 'W', Source.MEASURED),
            ),
            HardwareSample(
                timestamp='2026-06-19T10:00:01+08:00',
                power_watts=MetricValue(60.0, 'W', Source.MEASURED),
            ),
        ],
        sidecar={
            'p10': {
                'average_power_watts': {
                    'value': 90.0,
                    'note': 'manual fallback only',
                },
            },
        },
    )

    assert metrics['p10']['average_power_watts'] == {
        'value': 50.0,
        'unit': 'W',
        'source': 'derived',
        'note': '',
    }
