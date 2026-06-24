<script setup lang="ts">
import { computed } from 'vue'
import type { PipelineProgress } from '../api/analysis'
import { progressAriaLabel, progressCounterText, progressPercent } from '../utils/progressDisplay'

const props = defineProps<{
  readonly title: string
  readonly progress: PipelineProgress | null
  readonly taskId?: string
  readonly status?: string
  readonly batchIndex?: number
  readonly batchTotal?: number
}>()

const percent = () => progressPercent(props.progress)
const displayContext = computed(() => {
  if (!props.progress) return null
  return {
    title: props.title,
    progress: props.progress,
    batchIndex: props.batchIndex,
    batchTotal: props.batchTotal,
  }
})
</script>

<template>
  <div v-if="progress" class="progress-card" :class="`progress-${status || progress.stage_key}`">
    <div class="progress-card-head">
      <div>
        <span>{{ title }}</span>
        <strong>{{ progress.stage_label }}</strong>
      </div>
      <em>{{ displayContext ? progressCounterText(displayContext) : '' }}</em>
    </div>
    <div
      class="progress-track"
      role="progressbar"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-valuenow="percent()"
      :aria-label="displayContext ? progressAriaLabel(displayContext) : title"
    >
      <i :style="{ width: `${percent()}%` }" />
    </div>
    <p>{{ progress.stage_detail }}</p>
    <small v-if="taskId">任务 {{ taskId }} · {{ status || 'queued' }}</small>
  </div>
</template>
