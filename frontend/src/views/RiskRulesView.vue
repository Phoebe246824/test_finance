<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getRiskRules, updateRiskRules, type RiskRules } from '../api/riskRules'

const labels: Record<string, string> = {
  customer_identity: '客户身份',
  transaction_behavior: '交易行为',
  counterparty: '交易对手',
  amount_velocity: '金额频次',
  device_geo: '设备地域',
  history_context: '历史关联',
  compliance_signal: '合规信号',
}

const rules = ref<RiskRules>({
  thresholds: { high: 0.7, medium: 0.35 },
  dimension_weights: {},
  disposal_templates: { high: [], medium: [], low: [] },
})
const updatedAt = ref('')
const saving = ref(false)
const error = ref('')

async function load() {
  error.value = ''
  try {
    const data = await getRiskRules()
    rules.value = data.rules
    updatedAt.value = data.updated_at
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '加载规则失败'
  }
}

async function save() {
  saving.value = true
  error.value = ''
  try {
    const data = await updateRiskRules(rules.value)
    rules.value = data.rules
    updatedAt.value = data.updated_at
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '保存规则失败'
  } finally {
    saving.value = false
  }
}

function updateTemplate(level: 'high' | 'medium' | 'low', value: string) {
  rules.value.disposal_templates[level] = value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

function templateText(level: 'high' | 'medium' | 'low') {
  return (rules.value.disposal_templates[level] || []).join('\n')
}

function onTemplateInput(level: 'high' | 'medium' | 'low', event: Event) {
  updateTemplate(level, (event.target as HTMLTextAreaElement).value)
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>风险规则配置</h1>
      <p>维护风险阈值、维度权重和处置建议模板。</p>
    </div>
    <button class="button" :disabled="saving" @click="save">{{ saving ? '保存中...' : '保存配置' }}</button>
  </section>

  <div v-if="error" class="error">{{ error }}</div>

  <div class="grid-2">
    <div class="panel stack">
      <div class="section-title">
        <h2>风险阈值</h2>
        <span class="muted small">更新时间：{{ updatedAt || '未保存' }}</span>
      </div>
      <div class="field">
        <label>高风险阈值</label>
        <input v-model.number="rules.thresholds.high" class="input" type="number" min="0" max="1" step="0.01" />
      </div>
      <div class="field">
        <label>中风险阈值</label>
        <input v-model.number="rules.thresholds.medium" class="input" type="number" min="0" max="1" step="0.01" />
      </div>
      <p class="muted small">保存后，后端下一次风险评估会读取这里的阈值和维度权重重新计算 risk_score 与 risk_level。</p>
    </div>

    <div class="panel stack">
      <h2>维度权重</h2>
      <div v-for="(_, key) in rules.dimension_weights" :key="key" class="field">
        <label>{{ labels[String(key)] || key }}</label>
        <input v-model.number="rules.dimension_weights[String(key)]" class="input" type="number" min="0" max="1" step="0.01" />
      </div>
    </div>
  </div>

  <div class="panel stack" style="margin-top: 16px">
    <h2>处置建议模板</h2>
    <div class="grid-3">
      <div class="field">
        <label>高风险</label>
        <textarea class="textarea compact-textarea" :value="templateText('high')" @input="onTemplateInput('high', $event)" />
      </div>
      <div class="field">
        <label>中风险</label>
        <textarea class="textarea compact-textarea" :value="templateText('medium')" @input="onTemplateInput('medium', $event)" />
      </div>
      <div class="field">
        <label>低风险</label>
        <textarea class="textarea compact-textarea" :value="templateText('low')" @input="onTemplateInput('low', $event)" />
      </div>
    </div>
  </div>
</template>
