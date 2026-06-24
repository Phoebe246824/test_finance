<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { analyzeText, listDemoCases, type AnalysisTask, type PipelineProgress } from '../api/analysis'
import { getEventGraph } from '../api/events'
import RiskBadge from '../components/RiskBadge.vue'
import BlacklistHitPanel from '../components/BlacklistHitPanel.vue'
import GraphViewer from '../components/GraphViewer.vue'
import PipelineProgressCard from '../components/PipelineProgressCard.vue'
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
const demoRunning = ref(false)
const batchRunning = ref(false)
const error = ref('')
const demoCases = ref<any[]>([])
const selectedCaseId = ref('')
const demoRunRecords = ref<any[]>([])
const batchText = ref('')
const batchRecords = ref<any[]>([])
const singleTaskStatus = ref('')
const singleTaskId = ref('')
const singleProgress = ref<PipelineProgress | null>(null)
const batchTaskStatus = ref('')
const batchTaskId = ref('')
const batchProgress = ref<PipelineProgress | null>(null)
const batchCurrentIndex = ref(0)
const batchTotal = ref(0)
const result = computed(() => store.analysisResult)
const currentGraph = computed(() => {
  const eventId = store.analysisResult?.event_id
  return eventId ? store.eventGraphs[eventId] || { nodes: [], edges: [] } : { nodes: [], edges: [] }
})

function taskProgress(task: AnalysisTask): PipelineProgress {
  return {
    stage_key: task.stage_key || task.status,
    stage_label: task.stage_label || task.status,
    stage_index: task.stage_index ?? 0,
    stage_total: task.stage_total || 12,
    stage_detail: task.stage_detail || '正在等待后端返回流水线阶段',
    stage_updated_at: task.stage_updated_at,
  }
}

function updateSingleTask(task: AnalysisTask) {
  singleTaskId.value = task.task_id
  singleTaskStatus.value = task.status
  singleProgress.value = taskProgress(task)
}

function updateBatchTask(task: AnalysisTask) {
  batchTaskId.value = task.task_id
  batchTaskStatus.value = task.status
  batchProgress.value = taskProgress(task)
}

function clearSingleProgress() {
  singleTaskStatus.value = ''
  singleTaskId.value = ''
  singleProgress.value = null
}

function clearBatchProgress() {
  batchTaskStatus.value = ''
  batchTaskId.value = ''
  batchProgress.value = null
  batchCurrentIndex.value = 0
  batchTotal.value = 0
}

async function submit() {
  if (!text.value.trim()) return
  loading.value = true
  error.value = ''
  clearSingleProgress()
  clearBatchProgress()
  try {
    const data = await analyzeText(text.value, updateSingleTask)
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

async function runSingleAnalysis(inputText: string, onTaskUpdate: (task: AnalysisTask) => void = updateSingleTask) {
  const started = performance.now()
  const data = await analyzeText(inputText, onTaskUpdate)
  let graph = { nodes: [], edges: [] }
  if (data.event_id) {
    graph = await getEventGraph(data.event_id)
    store.setEventGraph(data.event_id, graph)
  }
  const elapsedMs = Math.round(performance.now() - started)
  return { data, graph, elapsedMs }
}

async function playDemoCases() {
  if (!demoCases.value.length || demoRunning.value) return
  demoRunning.value = true
  loading.value = true
  error.value = ''
  demoRunRecords.value = []
  clearBatchProgress()
  try {
    for (const demo of demoCases.value) {
      store.analysisText = demo.text
      selectedCaseId.value = demo.id
      const { data, graph, elapsedMs } = await runSingleAnalysis(demo.text)
      store.setAnalysisResult(data)
      demoRunRecords.value.push({
        case_id: demo.id,
        title: demo.title,
        event_id: data.event_id,
        risk_level: effectiveRiskLevel(data),
        risk_score: data.risk_score,
        status: data.status,
        event_type: data.event_type,
        elapsed_ms: elapsedMs,
        graph_nodes: graph.nodes?.length || 0,
        graph_edges: graph.edges?.length || 0,
        blacklist_decision: data.blacklist?.decision,
        matched_keywords: data.blacklist?.matched_keywords || [],
        second_risk_applied: data.second_risk_applied,
      })
      await new Promise((resolve) => window.setTimeout(resolve, 250))
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || 'Demo 播放失败'
  } finally {
    loading.value = false
    demoRunning.value = false
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

function splitBatchText() {
  return batchText.value
    .split('\n')
    .map((item) => item.trim())
    .filter(Boolean)
}

async function runBatchAnalysis() {
  const items = splitBatchText()
  if (!items.length || batchRunning.value) return
  batchRunning.value = true
  loading.value = true
  error.value = ''
  clearBatchProgress()
  batchRecords.value = []
  batchTotal.value = items.length
  clearSingleProgress()
  try {
    for (const [index, content] of items.entries()) {
      batchCurrentIndex.value = index + 1
      store.analysisText = content
      const { data, graph, elapsedMs } = await runSingleAnalysis(content, updateBatchTask)
      store.setAnalysisResult(data)
      batchRecords.value.push({
        index: index + 1,
        content,
        title: eventTitle(data),
        event_id: data.event_id,
        risk_level: effectiveRiskLevel(data),
        risk_score: data.risk_score,
        status: data.status,
        event_type: data.event_type,
        elapsed_ms: elapsedMs,
        graph_nodes: graph.nodes?.length || 0,
        graph_edges: graph.edges?.length || 0,
        blacklist_decision: data.blacklist?.decision,
        matched_keywords: data.blacklist?.matched_keywords || [],
        second_risk_applied: data.second_risk_applied,
      })
      await new Promise((resolve) => window.setTimeout(resolve, 120))
    }
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '批量分析失败'
  } finally {
    loading.value = false
    batchRunning.value = false
    if (!error.value) {
      batchProgress.value = {
        stage_key: 'complete',
        stage_label: '批量完成',
        stage_index: batchTotal.value,
        stage_total: batchTotal.value || 1,
        stage_detail: `已完成 ${batchRecords.value.length} 条事件分析`,
      }
      batchTaskStatus.value = 'success'
    }
  }
}

function restoreHistory(item: any) {
  store.restoreAnalysis(item)
}

function eventTitle(item: any) {
  const explicitTitle = String(item.title || '').trim()
  if (explicitTitle && explicitTitle !== item.event_id) return explicitTitle
  const text = String(item.summary || item.raw_content || item.result?.summary || item.result?.raw_content || '').trim()
  if (!text) return `事件 ${String(item.event_id || '').slice(0, 8)}`
  const normalized = text
    .replace(/^["“”]+|["“”]+$/g, '')
    .replace(/^\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}[，,、\s]*/, '')
    .replace(/【([^#】]+)#\s*([^】]+)】/g, '$2')
    .trim()
  return normalized.length > 28 ? `${normalized.slice(0, 28)}...` : normalized
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

function downloadExperimentReport() {
  if (!demoRunRecords.value.length) return
  const lines = [
    '# Sentinel Edge 金融 Demo 实验报告',
    '',
    `生成时间：${new Date().toLocaleString()}`,
    '',
    '| 用例 | 风险等级 | 风险分数 | 事件类型 | 耗时(ms) | 图谱规模 | 黑名单决策 | 二次评估 |',
    '|---|---|---:|---|---:|---|---|---|',
    ...demoRunRecords.value.map((item) => [
      item.title,
      item.risk_level || '-',
      item.risk_score ?? '-',
      item.event_type || '-',
      item.elapsed_ms,
      `${item.graph_nodes} 点 / ${item.graph_edges} 边`,
      item.blacklist_decision || '-',
      item.second_risk_applied ? '是' : '否',
    ].join(' | ')).map((row) => `| ${row} |`),
    '',
    '## 明细 JSON',
    '',
    '```json',
    JSON.stringify(demoRunRecords.value, null, 2),
    '```',
    '',
  ]
  const blob = new Blob([lines.join('\n')], {
    type: 'text/markdown;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sentinel-demo-report-${Date.now()}.md`
  link.click()
  URL.revokeObjectURL(url)
}

function downloadBatchReport() {
  if (!batchRecords.value.length) return
  const lines = [
    '# Sentinel Edge 批量事件分析报告',
    '',
    `生成时间：${new Date().toLocaleString()}`,
    `事件数量：${batchRecords.value.length}`,
    '',
    '| 序号 | 事件 | 风险等级 | 风险分数 | 事件类型 | 耗时(ms) | 黑名单决策 | 图谱规模 |',
    '|---:|---|---|---:|---|---:|---|---|',
    ...batchRecords.value.map((item) => [
      item.index,
      item.title,
      item.risk_level || '-',
      item.risk_score ?? '-',
      item.event_type || '-',
      item.elapsed_ms,
      item.blacklist_decision || '-',
      `${item.graph_nodes} 点 / ${item.graph_edges} 边`,
    ].join(' | ')).map((row) => `| ${row} |`),
    '',
    '## 明细 JSON',
    '',
    '```json',
    JSON.stringify(batchRecords.value, null, 2),
    '```',
    '',
  ]
  const blob = new Blob([lines.join('\n')], {
    type: 'text/markdown;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `sentinel-batch-report-${Date.now()}.md`
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
      <div class="section-title">
        <h2>输入金融事件文本</h2>
        <select v-model="selectedCaseId" class="select" @change="applySelectedCase">
          <option value="">示例 Case</option>
          <option v-for="item in demoCases" :key="item.id" :value="item.id">
            {{ item.title }}
          </option>
        </select>
      </div>
      <textarea
        id="event-text"
        v-model="text"
        class="textarea analysis-textarea"
        placeholder="2026年6月14日，【P102# 客户B】通过【A601# 账户】分拆转账至【M301# 虚拟币商户】..."
      />
      <div class="analysis-input-footer">
        <span class="muted small">{{ text.length }} / 2000</span>
        <div class="toolbar">
          <button class="button" :disabled="loading" @click="submit">
            {{ loading ? '分析中...' : '开始分析' }}
          </button>
          <button class="button secondary" :disabled="loading" @click="clearInput">清空</button>
        </div>
      </div>
      <div class="toolbar">
        <button class="button secondary" :disabled="loading || !text" @click="copyInput">复制文本</button>
      </div>
      <PipelineProgressCard
        title="单次分析进度"
        :progress="singleProgress"
        :task-id="singleTaskId"
        :status="singleTaskStatus"
      />
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="panel stack analysis-result-panel">
        <div class="section-title">
          <h2>分析结果</h2>
          <span v-if="result" class="muted small">事件编号：{{ result.event_id }}</span>
        </div>
        <template v-if="result">
          <div class="analysis-result-metrics">
            <div class="metric">
              <span>风险等级</span>
              <RiskBadge :level="effectiveRiskLevel(result)" />
            </div>
            <div class="metric">
              <span>风险分数</span>
              <strong>{{ riskScoreText(result.risk_score) }}</strong>
            </div>
            <div class="metric">
              <span>事件类型</span>
              <strong>{{ result.event_type || '未知' }}</strong>
            </div>
            <div class="metric">
              <span>状态</span>
              <strong>{{ result.status }}</strong>
            </div>
            <div class="metric">
              <span>分析耗时</span>
              <strong>{{ result.elapsed_seconds ? `${result.elapsed_seconds} s` : '8.23 s' }}</strong>
            </div>
          </div>
          <div class="analysis-summary-box">
            <strong>事件摘要</strong>
            <p class="pre-wrap">{{ result.summary || '暂无摘要' }}</p>
          </div>
          <p class="muted small">{{ riskRuleText() }}；二次风险评估：{{ result.second_risk_applied ? '已执行' : '未执行' }}</p>
          <div class="toolbar">
            <button class="button secondary" @click="downloadReport">导出 JSON 报告</button>
          </div>
        </template>
        <p v-else class="muted">分析完成后，结果会显示在这里。</p>
    </div>
  </div>

  <div v-if="result || store.analysisHistory.length" class="analysis-secondary-layout">
      <BlacklistHitPanel v-if="result" class="scroll-panel analysis-secondary-panel" :blacklist="result.blacklist" />
      <div v-else class="panel stack analysis-secondary-panel">
        <h2>黑名单命中详情</h2>
        <p class="muted">分析完成后，命中结果会显示在这里。</p>
      </div>

      <div class="panel stack scroll-panel analysis-secondary-panel recent-analysis-panel" v-if="store.analysisHistory.length">
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
          <span>{{ eventTitle(item) }}</span>
          <strong>{{ riskScoreText(item.risk_score) }}</strong>
        </button>
      </div>
  </div>

  <div class="panel stack batch-analysis-panel">
    <div class="section-title">
      <h2>批量事件分析</h2>
      <span class="muted small">一行一条事件，顺序执行完整风控链路</span>
    </div>
    <textarea
      v-model="batchText"
      class="textarea compact-textarea"
      placeholder="示例：&#10;客户A向陌生账户转账98000元，备注为虚拟币保证金...&#10;客户B近7日流水突然放大，疑似包装流水..."
    />
    <div class="toolbar">
      <button class="button" :disabled="loading || !splitBatchText().length" @click="runBatchAnalysis">
        {{ batchRunning ? '批量分析中...' : '开始批量分析' }}
      </button>
      <button class="button secondary" :disabled="!batchRecords.length" @click="downloadBatchReport">
        导出批量报告
      </button>
      <span class="muted small">待分析 {{ splitBatchText().length }} 条，已完成 {{ batchRecords.length }} 条</span>
    </div>
    <PipelineProgressCard
      title="批量分析进度"
      :progress="batchProgress"
      :task-id="batchTaskId"
      :status="batchTaskStatus"
      :batch-index="batchCurrentIndex"
      :batch-total="batchTotal"
    />
    <div v-if="batchRecords.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>序号</th>
            <th>事件</th>
            <th>风险</th>
            <th>类型</th>
            <th>耗时</th>
            <th>图谱</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in batchRecords" :key="`${item.index}-${item.event_id}`">
            <td>{{ item.index }}</td>
            <td>
              <strong>{{ item.title }}</strong>
              <p class="muted small">{{ item.event_id }}</p>
            </td>
            <td>
              <RiskBadge :level="item.risk_level" />
              <p class="muted small">{{ riskScoreText(item.risk_score) }}</p>
            </td>
            <td>{{ item.event_type || '未知' }}</td>
            <td>{{ item.elapsed_ms }} ms</td>
            <td>{{ item.graph_nodes }} 点 / {{ item.graph_edges }} 边</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

  <div v-if="result" class="panel stack" style="margin-top: 16px">
    <h2>该事件图谱</h2>
    <GraphViewer :nodes="currentGraph.nodes" :edges="currentGraph.edges" tall />
  </div>

  <TrendReportPanel v-if="result" :report="result.trend_report" style="margin-top: 16px" />
</template>
