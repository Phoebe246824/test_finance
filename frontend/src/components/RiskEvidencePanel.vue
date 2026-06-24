<script setup lang="ts">
import { computed } from 'vue'
import { effectiveRiskLevel, riskScoreText } from '../utils/risk'

const props = defineProps<{
  event: Record<string, any>
  rules?: Record<string, any> | null
}>()

const labels: Record<string, string> = {
  customer_identity: '客户身份',
  transaction_behavior: '交易行为',
  counterparty: '交易对手',
  amount_velocity: '金额频次',
  device_geo: '设备地域',
  history_context: '历史关联',
  compliance_signal: '合规信号',
}

const riskLevelName: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}

function scoreOf(value: any) {
  const score = typeof value === 'object' ? value?.score : value
  const number = Number(score || 0)
  return Number.isFinite(number) ? Math.max(0, Math.min(1, number)) : 0
}

function reasonOf(value: any) {
  if (typeof value === 'object') {
    return value?.reason || value?.evidence || value?.description || ''
  }
  return ''
}

const evidences = computed(() => {
  const event = props.event || {}
  const items: { title: string; description: string; tone?: string }[] = []
  const level = effectiveRiskLevel(event)
  items.push({
    title: '综合风险结论',
    description: `${riskLevelName[level] || level}，风险分数 ${riskScoreText(event.risk_score)}。`,
    tone: level,
  })

  for (const person of event.matched_persons || []) {
    items.push({ title: '人员黑名单命中', description: String(person), tone: 'high' })
  }
  for (const keyword of event.matched_keywords || []) {
    items.push({ title: '关键词命中', description: String(keyword), tone: 'medium' })
  }
  if (event.event_similarity?.hit) {
    items.push({
      title: '相似历史事件',
      description: `${event.event_similarity.event_id || '未知事件'}：${event.event_similarity.summary || '命中相似风险样本'}`,
      tone: 'medium',
    })
  }

  for (const [key, value] of Object.entries(event.dimension_scores || {})) {
    const score = scoreOf(value)
    if (score < 0.6) continue
    items.push({
      title: `${labels[key] || key}异常`,
      description: reasonOf(value) || `维度分数 ${score.toFixed(3)}，已达到重点关注水平。`,
      tone: score >= 0.85 ? 'high' : 'medium',
    })
  }

  if (event.second_risk_applied) {
    items.push({
      title: '历史回捞后二次评估',
      description: '该事件触发历史事件回捞，并完成补图后的二次风险评估。',
      tone: 'medium',
    })
  }

  return items
})

const suggestions = computed(() => {
  const level = effectiveRiskLevel(props.event || {})
  const templates = props.rules?.disposal_templates || {}
  const configured = templates[level]
  if (Array.isArray(configured) && configured.length) return configured
  if (level === 'high') {
    return ['建议立即人工复核并临时限制后续出金。', '核验客户身份、设备、收款账户和交易备注。']
  }
  if (level === 'medium') {
    return ['建议进入观察名单并补充客户回访。', '关注 24 小时内是否出现同账户、同设备或同收款方异常交易。']
  }
  return ['暂不拦截，保留为历史上下文。']
})
</script>

<template>
  <div class="panel stack">
    <div class="section-title">
      <h2>风险证据链</h2>
      <span class="muted small">可解释研判依据</span>
    </div>
    <div class="evidence-list">
      <div v-for="(item, index) in evidences" :key="`${item.title}-${index}`" class="evidence-item">
        <span class="evidence-index">{{ index + 1 }}</span>
        <div>
          <strong>{{ item.title }}</strong>
          <p class="muted small">{{ item.description }}</p>
        </div>
      </div>
    </div>
    <p v-if="!evidences.length" class="muted">暂无可展示证据。</p>

    <div class="section-title">
      <h2>处置建议</h2>
      <span class="muted small">基于风险等级与规则模板</span>
    </div>
    <div class="suggestion-list">
      <div v-for="(item, index) in suggestions" :key="`${item}-${index}`" class="suggestion-item">
        {{ item }}
      </div>
    </div>
  </div>
</template>

