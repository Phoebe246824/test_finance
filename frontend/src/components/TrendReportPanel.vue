<script setup lang="ts">
defineProps<{ report?: Record<string, any> | null }>()

function percent(value?: number) {
  if (value === null || value === undefined) return '未知'
  return `${Math.round(Number(value) * 100)}%`
}
</script>

<template>
  <div class="panel stack">
    <div class="section-title">
      <h2>趋势预测报告</h2>
      <span class="muted small">意图识别与后续风险演化</span>
    </div>
    <template v-if="report && Object.keys(report).length">
      <div class="grid-3">
        <div class="metric">
          <span>事件领域</span>
          <strong>{{ report.category_name || report.category || '未知' }}</strong>
          <p class="muted small">置信度 {{ percent(report.category_confidence) }}</p>
        </div>
        <div class="metric">
          <span>影响严重度</span>
          <strong>{{ report.severity_name || report.severity || '未知' }}</strong>
          <p class="muted small">置信度 {{ percent(report.severity_confidence) }}</p>
        </div>
        <div class="metric">
          <span>处置建议</span>
          <strong>{{ /冻结|拦截|复核/.test(report.report || '') ? '立即复核' : '持续观察' }}</strong>
        </div>
      </div>
      <div class="report-box pre-wrap">{{ report.report || '暂无报告正文' }}</div>
    </template>
    <p v-else class="muted">该事件尚未生成趋势预测报告。通常只有进入后续分析流程的风险事件会生成。</p>
  </div>
</template>
