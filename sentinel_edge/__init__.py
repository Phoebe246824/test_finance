"""Edge deployment helpers for the Sentinel competition build."""

from sentinel_edge.hardware import collect_hardware_profile
from sentinel_edge.metrics import BenchmarkRecorder

__all__ = ["BenchmarkRecorder", "collect_hardware_profile"]
