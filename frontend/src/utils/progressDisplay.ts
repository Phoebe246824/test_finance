import type { PipelineProgress } from '../api/analysis'

export interface ProgressDisplayContext {
  readonly title: string
  readonly progress: PipelineProgress
  readonly batchIndex?: number
  readonly batchTotal?: number
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function finiteNumber(value: number | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function progressPercent(progress: PipelineProgress | null): number {
  if (!progress || progress.stage_total <= 0) return 0
  return clamp(Math.round((progress.stage_index / progress.stage_total) * 100), 0, 100)
}

export function progressCounterText(context: ProgressDisplayContext): string {
  const total = finiteNumber(context.batchTotal)
  const index = finiteNumber(context.batchIndex)
  if (total !== null && total > 0 && index !== null && index > 0) {
    return `第 ${clamp(Math.round(index), 0, total)} / ${Math.round(total)} 条`
  }
  return `${context.progress.stage_index} / ${context.progress.stage_total}`
}

export function progressAriaLabel(context: ProgressDisplayContext): string {
  return `${context.title}：${context.progress.stage_label}，${progressCounterText(context)}`
}
