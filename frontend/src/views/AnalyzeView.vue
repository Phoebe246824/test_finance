<script setup lang="ts">
import { computed, ref } from 'vue'
import { analyzeText } from '../api/analysis'
import { getEventGraph } from '../api/events'
import RiskBadge from '../components/RiskBadge.vue'
import BlacklistHitPanel from '../components/BlacklistHitPanel.vue'
import GraphViewer from '../components/GraphViewer.vue'
import TrendReportPanel from '../components/TrendReportPanel.vue'
import { useWorkbenchStore } from '../stores/workbench'
import { effectiveRiskLevel, riskRuleText, riskScoreText } from '../utils/risk'

const store = useWorkbenchStore()
const text = computed({
  get: () => store.analysisText,
  set: (value) => {
    store.analysisText = value
  },
})
const loading = ref(false)
const error = ref('')
const result = computed(() => store.analysisResult)
const currentGraph = computed(() => {
  const eventId = store.analysisResult?.event_id
  return eventId ? store.eventGraphs[eventId] || { nodes: [], edges: [] } : { nodes: [], edges: [] }
})

async function submit() {
  if (!text.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    const data = await analyzeText(text.value)
    store.setAnalysisResult(data)
    if (data.event_id) {
      store.setEventGraph(data.event_id, await getEventGraph(data.event_id))
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '分析失败'
  } finally {
    loading.value = false
  }
}

function fillSample() {
  store.analysisText = `2026年6月14日 23:48，【P102# 客户B】再次通过手机银行向4个新开户账户分散转出 196000 元，随后其中两个收款账户在10分钟内继续转入同一虚拟币平台商户【M301# 虚拟币商户】。交易行为疑似分拆交易与洗钱资金归集，反洗钱系统要求立即复核并冻结后续出金。`
}
</script>

<template>
  <section class="page-header">
    <div>
      <h1>风险分析</h1>
      <p>输入金融事件文本，执行黑名单过滤、风险评估、事件分类和图谱补全。</p>
    </div>
  </section>

  <div class="grid-2">
    <div class="panel stack">
      <div class="field">
        <label for="event-text">事件内容</label>
        <textarea id="event-text" v-model="text" class="textarea" />
      </div>
      <div class="toolbar">
        <button class="button" :disabled="loading" @click="submit">
          {{ loading ? '分析中...' : '开始分析' }}
        </button>
        <button class="button secondary" :disabled="loading" @click="fillSample">填入示例</button>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="stack">
      <div class="panel stack">
        <h2>分析结果</h2>
        <template v-if="result">
          <div class="grid-3">
            <div class="metric">
              <span>风险等级</span>
              <RiskBadge :level="effectiveRiskLevel(result)" />
            </div>
            <div class="metric">
              <span>风险分数</span>
              <strong>{{ riskScoreText(result.risk_score) }}</strong>
            </div>
            <div class="metric">
              <span>状态</span>
              <strong>{{ result.status }}</strong>
            </div>
          </div>
          <p class="pre-wrap">{{ result.summary || '暂无摘要' }}</p>
          <p class="muted small">{{ riskRuleText() }}</p>
          <p class="muted small">事件编号：{{ result.event_id }}</p>
          <p class="muted small">二次风险评估：{{ result.second_risk_applied ? '已执行' : '未执行' }}</p>
        </template>
        <p v-else class="muted">分析完成后，结果会显示在这里。</p>
      </div>

      <BlacklistHitPanel v-if="result" :blacklist="result.blacklist" />
    </div>
  </div>

  <div v-if="result" class="panel stack" style="margin-top: 16px">
    <h2>该事件图谱</h2>
    <GraphViewer :nodes="currentGraph.nodes" :edges="currentGraph.edges" tall />
  </div>

  <TrendReportPanel v-if="result" :report="result.trend_report" style="margin-top: 16px" />
</template>
