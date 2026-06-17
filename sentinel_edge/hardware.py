"""Hardware and local inference environment discovery.

The checks in this module are intentionally best-effort. They work on the
current developer machine and become more informative on the AMD Ryzen AI
MAX+ cloud workstation when ROCm / Ryzen AI tools are installed.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class HardwareProfile:
    target_platform: str
    os: str
    python: str
    cpu: str
    memory_gb: float | None
    gpu_backend: str
    gpu_detected: bool
    npu_backend: str
    npu_detected: bool = False
    gpu_details: list[str] = field(default_factory=list)
    npu_details: list[str] = field(default_factory=list)
    local_llm_endpoint: str = ""
    local_llm_model: str = ""
    local_embedder_model: str = ""
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _run_command(command: list[str], timeout: float = 5.0) -> str:
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return "\n".join(
        part.strip() for part in (completed.stdout, completed.stderr) if part.strip()
    )


def _memory_gb() -> float | None:
    if platform.system() == "Darwin":
        output = _run_command(["sysctl", "-n", "hw.memsize"])
        if output.strip().isdigit():
            return round(int(output.strip()) / (1024**3), 2)

    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemTotal:"):
                parts = line.split()
                if len(parts) >= 2 and parts[1].isdigit():
                    return round(int(parts[1]) / (1024**2), 2)
    return None


def _cpu_name() -> str:
    if platform.system() == "Darwin":
        output = _run_command(["sysctl", "-n", "machdep.cpu.brand_string"])
        if output:
            return output.splitlines()[0]
    return platform.processor() or platform.machine() or "unknown"


def _detect_gpu() -> tuple[bool, str, list[str]]:
    details: list[str] = []
    backend = os.getenv("SENTINEL_GPU_BACKEND", "").strip()

    if shutil.which("rocm-smi"):
        output = _run_command(["rocm-smi", "--showproductname"], timeout=8.0)
        if output:
            details.extend(output.splitlines()[:12])
        return True, backend or "rocm", details

    if shutil.which("rocminfo"):
        output = _run_command(["rocminfo"], timeout=8.0)
        interesting = [
            line.strip()
            for line in output.splitlines()
            if "Radeon" in line or "gfx" in line or "Marketing Name" in line
        ]
        if interesting:
            details.extend(interesting[:12])
            return True, backend or "rocm", details

    if shutil.which("lspci"):
        output = _run_command(["lspci"], timeout=5.0)
        interesting = [
            line for line in output.splitlines() if "AMD" in line and "VGA" in line
        ]
        if interesting:
            details.extend(interesting[:8])
            return True, backend or "linux-display", details

    return False, backend or "not-detected", details


def _detect_npu() -> tuple[bool, str, list[str]]:
    details: list[str] = []
    backend = os.getenv("SENTINEL_NPU_BACKEND", "").strip()
    ryzen_ai_home = os.getenv("RYZEN_AI_HOME") or os.getenv("RYZENAI_HOME")

    if ryzen_ai_home:
        details.append(f"Ryzen AI SDK home: {ryzen_ai_home}")
        return True, backend or "ryzen-ai-sdk", details

    for command in (["xrt-smi", "examine"], ["xbutil", "examine"]):
        if shutil.which(command[0]):
            output = _run_command(command, timeout=8.0)
            if output:
                details.extend(output.splitlines()[:12])
                return True, backend or "xrt", details

    return False, backend or "not-detected", details


def collect_hardware_profile() -> HardwareProfile:
    gpu_detected, gpu_backend, gpu_details = _detect_gpu()
    npu_detected, npu_backend, npu_details = _detect_npu()

    notes: list[str] = []
    if not gpu_detected:
        notes.append(
            "GPU tools were not found; set SENTINEL_GPU_BACKEND after ROCm is installed."
        )
    if not npu_detected:
        notes.append(
            "NPU tools were not found; set RYZEN_AI_HOME or SENTINEL_NPU_BACKEND after Ryzen AI SDK is installed."
        )

    return HardwareProfile(
        target_platform=os.getenv(
            "SENTINEL_TARGET_PLATFORM", "AMD Ryzen AI MAX+ 395 Mini AI Workstation"
        ),
        os=f"{platform.system()} {platform.release()}",
        python=platform.python_version(),
        cpu=_cpu_name(),
        memory_gb=_memory_gb(),
        gpu_backend=gpu_backend,
        gpu_detected=gpu_detected,
        gpu_details=gpu_details,
        npu_backend=npu_backend,
        npu_detected=npu_detected,
        npu_details=npu_details,
        local_llm_endpoint=os.getenv("LLM_BASE_URL", ""),
        local_llm_model=os.getenv("LLM_MODEL", ""),
        local_embedder_model=os.getenv("EMBEDDER_MODEL", ""),
        notes=notes,
    )
