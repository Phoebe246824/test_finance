from datetime import datetime

from sentinel_edge.evidence.hardware_sampler import parse_rocm_smi_output, sample_once
from sentinel_edge.evidence.models import Source


def test_parse_rocm_smi_output_extracts_use_power_and_ignores_vram_percent():
    output = """
    GPU use (%) : 87
    GPU Memory Allocated (VRAM%) : 42
    Average Graphics Package Power (W) : 58.0
    """

    parsed = parse_rocm_smi_output(output)

    assert parsed == {
        "gpu_util_percent": 87.0,
        "vram_used_mb": None,
        "power_watts": 58.0,
    }


def test_sample_once_marks_missing_rocm_output_not_available():
    sample = sample_once(command_runner=lambda _command: "")

    assert sample.raw_output == ""
    for metric in (
        sample.gpu_util_percent,
        sample.vram_used_mb,
        sample.power_watts,
    ):
        assert metric.value is None
        assert metric.source in {Source.NOT_AVAILABLE, Source.NOT_AVAILABLE.value}
        assert "rocm-smi output missing or unsupported" in metric.note


def test_sample_once_records_measured_metrics_from_parseable_output():
    commands: list[list[str]] = []
    raw_output = """
    GPU[0] : GPU use (%) : 87
    GPU[0] : VRAM Used Memory (MB) : 6144
    GPU[0] : Average Graphics Package Power (W) : 58.0
    """

    def runner(command: list[str]) -> str:
        commands.append(command)
        return raw_output

    sample = sample_once(command_runner=runner)
    parsed_timestamp = datetime.fromisoformat(sample.timestamp)

    assert commands == [
        [
            "rocm-smi",
            "--showuse",
            "--showmemuse",
            "--showpower",
            "--showmeminfo",
            "vram",
        ],
    ]
    assert sample.timestamp == parsed_timestamp.isoformat(timespec="seconds")
    assert sample.gpu_util_percent.value == 87.0
    assert sample.gpu_util_percent.unit == "%"
    assert sample.gpu_util_percent.source == Source.MEASURED
    assert sample.vram_used_mb.value == 6144.0
    assert sample.vram_used_mb.unit == "MB"
    assert sample.vram_used_mb.source == Source.MEASURED
    assert sample.power_watts.value == 58.0
    assert sample.power_watts.unit == "W"
    assert sample.power_watts.source == Source.MEASURED
    assert sample.raw_output == raw_output


def test_parse_rocm_smi_output_extracts_vram_megabytes():
    output = """
    GPU use : 71 %
    VRAM Used Memory (MB): 6144
    Package Power (W): 47.5
    """

    parsed = parse_rocm_smi_output(output)

    assert parsed["gpu_util_percent"] == 71.0
    assert parsed["vram_used_mb"] == 6144.0
    assert parsed["power_watts"] == 47.5


def test_parse_rocm_smi_output_converts_vram_bytes_to_megabytes():
    output = """
    GPU[0] : VRAM Total Used Memory (B): 4294967296
    GPU[0] : GPU Memory Allocated (VRAM%) : 42
    """

    parsed = parse_rocm_smi_output(output)

    assert parsed["vram_used_mb"] == 4096.0


def test_parse_rocm_smi_output_ignores_gpu_index_when_values_are_unparseable():
    output = """
    GPU[0] : GPU use (%) : N/A
    GPU[0] : VRAM Used Memory (MB) : N/A
    GPU[0] : Average Graphics Package Power (W) : unsupported
    """

    parsed = parse_rocm_smi_output(output)

    assert parsed == {
        "gpu_util_percent": None,
        "vram_used_mb": None,
        "power_watts": None,
    }


def test_parse_rocm_smi_output_extracts_unit_adjacent_values_without_colons():
    output = """
    GPU[0] GPU use 88 %
    GPU[0] Memory Used 2048 MB
    GPU[0] Package Power 52.5 W
    """

    parsed = parse_rocm_smi_output(output)

    assert parsed == {
        "gpu_util_percent": 88.0,
        "vram_used_mb": 2048.0,
        "power_watts": 52.5,
    }
