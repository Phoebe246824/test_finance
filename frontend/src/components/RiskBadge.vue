<script setup lang="ts">
defineProps<{ level?: string | null }>()

function label(level?: string | null) {
  if (level === 'high') return '高风险'
  if (level === 'medium') return '中风险'
  if (level === 'low') return '低风险'
  return '未知'
}
</script>

<template>
  <span :class="['risk-badge', `risk-${level || 'unknown'}`]">{{ label(level) }}</span>
</template>
