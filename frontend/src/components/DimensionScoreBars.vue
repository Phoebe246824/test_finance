<script setup lang="ts">
defineProps<{ scores?: Record<string, any> | null }>()

const labels: Record<string, string> = {
  customer_identity: '客户身份',
  transaction_behavior: '交易行为',
  counterparty: '交易对手',
  amount_velocity: '金额频次',
  device_geo: '设备地域',
  history_context: '历史关联',
  compliance_signal: '合规信号',
}

function scoreOf(value: any) {
  const score = typeof value === 'object' ? value?.score : value
  const number = Number(score || 0)
  return Number.isFinite(number) ? Math.max(0, Math.min(1, number)) : 0
}
</script>

<template>
  <div class="bars">
    <div v-for="(value, key) in scores || {}" :key="key" class="bar-row">
      <div class="bar-label">
        <span>{{ labels[String(key)] || key }}</span>
        <span>{{ scoreOf(value).toFixed(3) }}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" :style="{ width: `${scoreOf(value) * 100}%` }"></div>
      </div>
    </div>
    <p v-if="!scores || !Object.keys(scores).length" class="muted small">暂无维度分数</p>
  </div>
</template>
