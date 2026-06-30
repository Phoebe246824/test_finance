<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { getDashboardOverview } from '../api/dashboard'
import RiskBadge from '../components/RiskBadge.vue'
import { effectiveRiskLevel, riskScoreText } from '../utils/risk'

const data = ref<any>(null)
const loading = ref(false)
const error = ref('')

const riskLabels: Record<string, string> = {
  high: '高风险',
  medium: '中风险',
  low: '低风险',
}

const riskColors: Record<string, string> = {
  high: '#ed3434',
  medium: '#f3b32a',
  low: '#2f72ff',
}

type TrendRow = {
  date?: string
  label: string
  high: number
  medium: number
  low: number
}

function eventTitle(event: any) {
  const explicitTitle = String(event.title || '').trim()
  if (explicitTitle && explicitTitle !== event.event_id) return explicitTitle
  const text = String(event.summary || event.raw_content || '').trim()
  if (!text) return `事件 ${String(event.event_id || '').slice(0, 8)}`
  return text.length > 28 ? `${text.slice(0, 28)}...` : text
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    data.value = await getDashboardOverview()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '加载总览失败'
  } finally {
    loading.value = false
  }
}

function percent(value?: number | null) {
  if (value === null || value === undefined) return '0%'
  return `${Math.round(Number(value) * 100)}%`
}

const recentEvents = computed(() => data.value?.recent_events || [])
const highRiskEvents = computed(() =>
  recentEvents.value.filter((event: any) => effectiveRiskLevel(event) === 'high'),
)
const pagedHighRiskEvents = computed(() => highRiskEvents.value.slice(0, 6))
const riskDistributionItems = computed(() => {
  const distribution = data.value?.risk_distribution || {}
  return ['high', 'medium', 'low'].map((key) => ({
    key,
    label: riskLabels[key],
    value: Number(distribution[key] || 0),
    color: riskColors[key],
  }))
})
const riskConic = computed(() => {
  const total = riskDistributionItems.value.reduce((sum, item) => sum + item.value, 0)
  if (!total) return 'conic-gradient(#e7eef8 0deg 360deg)'
  let cursor = 0
  const stops = riskDistributionItems.value.map((item) => {
    const start = cursor
    cursor += (item.value / total) * 360
    return `${item.color} ${start}deg ${cursor}deg`
  })
  return `conic-gradient(${stops.join(', ')})`
})
const trendRows = computed(() => {
  return (data.value?.risk_trend || []) as TrendRow[]
})
const trendPolylineHigh = computed(() => makeTrendPolyline('high'))
const trendPolylineMedium = computed(() => makeTrendPolyline('medium'))
const trendPolylineLow = computed(() => makeTrendPolyline('low'))
let refreshTimer: number | undefined

function makeTrendPolyline(key: 'high' | 'medium' | 'low') {
  const rows = trendRows.value
  const maxValue = Math.max(1, ...rows.flatMap((row) => [row.high, row.medium, row.low]))
  return rows.map((row: TrendRow, index: number) => {
    const x = 34 + index * 80
    const y = 176 - (row[key] / maxValue) * 132
    return `${x},${y}`
  }).join(' ')
}

function eventTime(event: any) {
  return event.updated_at || event.created_at || '-'
}

function deltaText(key: string, suffix = '') {
  const delta = data.value?.metric_deltas?.[key]
  if (!delta) return '较昨日 0'
  const value = Number(delta.value || 0)
  if (value === 0) return `较昨日 0${suffix}`
  return `较昨日 ${value > 0 ? '+' : ''}${suffix === '%' ? Math.round(value * 100) : value}${suffix}`
}

function deltaClass(key: string) {
  const direction = data.value?.metric_deltas?.[key]?.direction
  return direction === 'down' ? 'success-text' : direction === 'up' ? 'danger-text' : ''
}

function hitType(event: any) {
  const parts = []
  if (event.matched_persons?.length) parts.push('人员')
  if (event.matched_keywords?.length) parts.push('关键词')
  if (event.event_similarity?.hit) parts.push('相似事件')
  return parts.length ? parts.join('、') : event.blacklist_decision || '相关事件'
}

onMounted(load)
onMounted(() => {
  refreshTimer = window.setInterval(load, 30000)
})
onUnmounted(() => {
  if (refreshTimer !== undefined) window.clearInterval(refreshTimer)
})
</script>

<template>
  <section class="page-header">
    <div>
      <h1>风控总览</h1>
      <p>汇总事件风险、趋势报告、待复核任务和最近处理记录。</p>
    </div>
    <div class="toolbar">
      <span class="muted small">刷新时间：{{ new Date().toLocaleString() }}</span>
      <button class="button secondary icon-refresh" :disabled="loading" title="刷新" @click="load">↻</button>
      <RouterLink class="button" to="/analysis">新增分析</RouterLink>
    </div>
  </section>

  <div v-if="error" class="error">{{ error }}</div>

  <template v-if="data">
    <div class="grid-4">
      <div class="metric kpi">
        <span class="kpi-icon kpi-icon-events" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M7 3h7l4 4v14H7z" /><path d="M14 3v5h5M10 12h6M10 16h4" /></svg>
        </span>
        <span>事件总数</span>
        <strong>{{ data.metrics.total_events }}</strong>
        <em :class="deltaClass('total_events')">{{ deltaText('total_events') }}</em>
      </div>
      <div class="metric kpi">
        <span class="kpi-icon kpi-icon-risk" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 3 21 20H3z" /><path d="M12 9v4M12 17h.01" /></svg>
        </span>
        <span>高风险事件</span>
        <strong>{{ data.metrics.high_risk_events }}</strong>
        <em :class="deltaClass('high_risk_events')">{{ deltaText('high_risk_events') }}</em>
      </div>
      <div class="metric kpi">
        <span class="kpi-icon kpi-icon-review" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M5 4h14v16H5z" /><path d="m8 12 2.5 2.5L16 9M8 17h8" /></svg>
        </span>
        <span>待复核</span>
        <strong>{{ data.metrics.pending_review }}</strong>
        <em :class="deltaClass('pending_review')">{{ deltaText('pending_review') }}</em>
      </div>
      <div class="metric kpi">
        <span class="kpi-icon kpi-icon-trend" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M4 19h16" /><path d="m5 15 4-4 4 3 6-8" /><path d="M16 6h3v3" /></svg>
        </span>
        <span>趋势报告覆盖率</span>
        <strong>{{ percent(data.metrics.trend_report_coverage) }}</strong>
        <em :class="deltaClass('trend_report_coverage')">{{ deltaText('trend_report_coverage', '%') }}</em>
      </div>
      <div class="metric kpi">
        <span class="kpi-icon kpi-icon-blacklist" aria-hidden="true">
          <svg viewBox="0 0 24 24"><path d="M12 3 19 6v5c0 5-3 8-7 10-4-2-7-5-7-10V6z" /><path d="M9 9l6 6M15 9l-6 6" /></svg>
        </span>
        <span>黑名单命中数</span>
        <strong>{{ data.metrics.blacklist_hit_events }}</strong>
        <em :class="deltaClass('blacklist_hit_events')">{{ deltaText('blacklist_hit_events') }}</em>
      </div>
    </div>

    <div class="dashboard-prototype-grid">
      <div class="panel stack dashboard-compact-panel">
        <div class="section-title">
          <h2>风险等级分布</h2>
        </div>
        <div class="donut-layout">
          <div class="risk-donut" :style="{ background: riskConic }">
            <span></span>
          </div>
          <div class="risk-donut-legend">
            <div v-for="item in riskDistributionItems" :key="item.key" class="legend-row">
              <i :style="{ background: item.color }"></i>
              <span>{{ item.label }}</span>
              <strong>{{ item.value }} ({{ data.metrics.total_events ? ((item.value / data.metrics.total_events) * 100).toFixed(1) : '0.0' }}%)</strong>
            </div>
          </div>
        </div>
      </div>

      <div class="panel stack dashboard-compact-panel trend-panel">
        <div class="section-title">
          <h2>风险趋势（近7天）</h2>
          <div class="chart-legend">
            <span><i class="high-dot"></i>高风险</span>
            <span><i class="medium-dot"></i>中风险</span>
            <span><i class="low-dot"></i>低风险</span>
          </div>
        </div>
        <div class="trend-chart">
          <svg viewBox="0 0 560 210" role="img" aria-label="风险趋势">
            <g class="grid-lines">
              <line v-for="y in [44, 77, 110, 143, 176]" :key="y" x1="30" :y1="y" x2="530" :y2="y" />
            </g>
            <polyline class="trend-line high" :points="trendPolylineHigh" />
            <polyline class="trend-line medium" :points="trendPolylineMedium" />
            <polyline class="trend-line low" :points="trendPolylineLow" />
            <g v-for="row in trendRows" :key="row.label">
              <text :x="34 + trendRows.indexOf(row) * 80" y="200">{{ row.label }}</text>
            </g>
          </svg>
        </div>
      </div>
    </div>

    <div class="dashboard-grid-wide prototype-table-grid">
      <div class="panel stack">
        <div class="section-title">
          <h2>最新高风险事件</h2>
          <RouterLink class="button secondary" to="/events">查看事件库</RouterLink>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>事件ID</th>
                <th>标题</th>
                <th>风险等级</th>
                <th>风险分数</th>
                <th>命中类型</th>
                <th>类型</th>
                <th>时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="event in pagedHighRiskEvents" :key="event.event_id">
                <td class="small">{{ event.event_id }}</td>
                <td><strong>{{ eventTitle(event) }}</strong></td>
                <td>
                  <RiskBadge :level="effectiveRiskLevel(event)" />
                </td>
                <td>{{ riskScoreText(event.risk_score) }}</td>
                <td>{{ hitType(event) }}</td>
                <td>{{ event.event_type || '未知' }}</td>
                <td class="muted small">{{ eventTime(event) }}</td>
                <td><RouterLink class="table-action" :to="`/events/${event.event_id}`">查看</RouterLink></td>
              </tr>
              <tr v-if="!pagedHighRiskEvents.length">
                <td colspan="8" class="muted">暂无高风险事件</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel stack dashboard-review-panel">
        <div class="section-title">
          <h2>高频命中词</h2>
          <span class="muted small">黑名单关键词</span>
        </div>
        <div class="hit-list">
          <span v-for="item in data.top_keywords" :key="item.name" class="chip">
            {{ item.name }} x{{ item.value }}
          </span>
          <span v-if="!data.top_keywords.length" class="muted small">暂无关键词命中</span>
        </div>
      </div>
    </div>
  </template>
</template>
