from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

PIPELINE_STAGE_TOTAL: Final = 12


@dataclass(frozen=True, slots=True)
class PipelineProgress:
    stage_key: str
    stage_label: str
    stage_index: int
    stage_total: int
    stage_detail: str

    def as_task_values(self) -> dict[str, int | str]:
        return {
            "stage_key": self.stage_key,
            "stage_label": self.stage_label,
            "stage_index": self.stage_index,
            "stage_total": self.stage_total,
            "stage_detail": self.stage_detail,
        }


ProgressCallback = Callable[[PipelineProgress], None]


def pipeline_progress(
    stage_key: str,
    stage_label: str,
    stage_index: int,
    stage_detail: str,
) -> PipelineProgress:
    return PipelineProgress(
        stage_key=stage_key,
        stage_label=stage_label,
        stage_index=stage_index,
        stage_total=PIPELINE_STAGE_TOTAL,
        stage_detail=stage_detail,
    )
