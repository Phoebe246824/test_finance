<script setup lang="ts">
import type { PipelineProgress } from '../api/analysis'

const props = defineProps<{
  readonly title: string
  readonly progress: PipelineProgress | null
  readonly taskId?: string
  readonly status?: string
  readonly batchIndex?: number
  readonly batchTotal?: number
}>()

function percent(progress: PipelineProgress | null) {
  if (!progress || progress.stage_total <= 0) return 0
  return Math.min(100, Math.max(0, Math.round((progress.stage_index / progress.stage_total) * 100)))
}
</script>

<template>
  <div v-if="progress" class="progress-card" :class="`progress-${status || progress.stage_key}`">
    <div class="progress-card-head">
      <div>
        <span>{{ title }}</span>
        <strong>{{ progress.stage_label }}</strong>
      </div>
      <em v-if="batchIndex && batchTotal">第 {{ batchIndex }} / {{ batchTotal }} 条</em>
      <em v-else>{{ progress.stage_index }} / {{ progress.stage_total }}</em>
    </div>
    <div class="progress-track" aria-hidden="true">
      <i :style="{ width: `${percent(progress)}%` }" />
    </div>
    <p>{{ progress.stage_detail }}</p>
    <small v-if="taskId">任务 {{ taskId }} · {{ status || 'queued' }}</small>
  </div>
</template>
