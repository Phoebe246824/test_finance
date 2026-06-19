<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { analyzeText, listDemoCases } from '../api/analysis'
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
const demoCases = ref<any[]>([])
const selectedCaseId = ref('')
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

async function loadDemoCases() {
  try {
    const data = await listDemoCases()
    demoCases.value = data.items || []
  } catch {
    demoCases.value = []
  }
}

function applySelectedCase() {
  const item = demoCases.value.find((demo) => demo.id === selectedCaseId.value)
  if (item) store.analysisText = item.text
}

function clearInput() {
  store.analysisText = ''
}

async function copyInput() {
  if (text.value) await navigator.clipboard.writeText(text.value)
}

function restoreHistory(item: any) {
  store.restoreAnalysis(item)
}

function downloadReport() {
  if (!result.value) return
  const payload = {
    exported_at: new Date().toISOString(),
    analysis: result.value,
    graph: currentGraph.value,
  }
  const blob = new Blob([JSON.stringify(payload, null, 2)], {
    type: 'application/json;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sentinel-analysis-${result.value.event_id || Date.now()}.json`
  link.click()
  URL.revokeObjectURL(url)
}

onMounted(loadDemoCases)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>风险分析</h1>
      <p>输入金融事件文本，执行黑名单过滤、风险评估、事件分类和图谱补全。</p>
    </div>
  </section>

  <div class="analysis-layout">
    <div class="panel stack analysis-input-panel">
      <div class="toolbar">
        <select v-model="selectedCaseId" class="select" @change="applySelectedCase">
          <option value="">选择 Demo case</option>
          <option v-for="item in demoCases" :key="item.id" :value="item.id">
            {{ item.title }}
          </option>
        </select>
      </div>
      <div class="field">
        <label for="event-text">事件内容</label>
        <textarea id="event-text" v-model="text" class="textarea analysis-textarea" />
      </div>
      <div class="toolbar">
        <button class="button" :disabled="loading" @click="submit">
          {{ loading ? '分析中...' : '开始分析' }}
        </button>
        <button class="button secondary" :disabled="loading || !text" @click="copyInput">复制文本</button>
        <button class="button secondary" :disabled="loading" @click="clearInput">清空</button>
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
          <button class="button secondary" @click="downloadReport">导出 JSON 报告</button>
        </template>
        <p v-else class="muted">分析完成后，结果会显示在这里。</p>
      </div>

      <BlacklistHitPanel v-if="result" :blacklist="result.blacklist" />

      <div class="panel stack" v-if="store.analysisHistory.length">
        <div class="section-title">
          <h2>最近分析</h2>
          <span class="muted small">保留最近 8 条</span>
        </div>
        <button
          v-for="item in store.analysisHistory"
          :key="item.event_id"
          class="history-item"
          @click="restoreHistory(item)"
        >
          <span>{{ item.summary || item.event_id }}</span>
          <strong>{{ riskScoreText(item.risk_score) }}</strong>
        </button>
      </div>
    </div>
  </div>

  <div v-if="result" class="panel stack" style="margin-top: 16px">
    <h2>该事件图谱</h2>
    <GraphViewer :nodes="currentGraph.nodes" :edges="currentGraph.edges" tall />
  </div>

  <TrendReportPanel v-if="result" :report="result.trend_report" style="margin-top: 16px" />
</template>
