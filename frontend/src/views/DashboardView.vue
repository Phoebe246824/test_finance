<script setup lang="ts">
import { onMounted, ref } from 'vue'
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

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>风控总览</h1>
      <p>汇总事件风险、趋势报告、待复核任务和最近处理记录。</p>
    </div>
    <div class="toolbar">
      <button class="button secondary" :disabled="loading" @click="load">刷新</button>
      <RouterLink class="button" to="/analysis">新增分析</RouterLink>
    </div>
  </section>

  <div v-if="error" class="error">{{ error }}</div>

  <template v-if="data">
    <div class="grid-4">
      <div class="metric kpi">
        <span>事件总数</span>
        <strong>{{ data.metrics.total_events }}</strong>
      </div>
      <div class="metric kpi">
        <span>高风险事件</span>
        <strong>{{ data.metrics.high_risk_events }}</strong>
      </div>
      <div class="metric kpi">
        <span>待复核</span>
        <strong>{{ data.metrics.pending_review }}</strong>
      </div>
      <div class="metric kpi">
        <span>趋势报告覆盖率</span>
        <strong>{{ percent(data.metrics.trend_report_coverage) }}</strong>
      </div>
    </div>

    <div class="dashboard-grid">
      <div class="panel stack">
        <div class="section-title">
          <h2>风险分布</h2>
          <span class="muted small">按当前展示规则统计</span>
        </div>
        <div class="risk-distribution">
          <div v-for="(value, key) in data.risk_distribution" :key="key" class="risk-row">
            <span>{{ riskLabels[String(key)] || key }}</span>
            <div class="bar-track">
              <div
                class="bar-fill"
                :style="{ width: `${data.metrics.total_events ? (Number(value) / data.metrics.total_events) * 100 : 0}%` }"
              ></div>
            </div>
            <strong>{{ value }}</strong>
          </div>
        </div>
      </div>

      <div class="panel stack">
        <div class="section-title">
          <h2>事件类型</h2>
          <span class="muted small">Top categories</span>
        </div>
        <div v-for="item in data.event_type_distribution.slice(0, 6)" :key="item.name" class="list-row">
          <span>{{ item.name }}</span>
          <strong>{{ item.value }}</strong>
        </div>
        <p v-if="!data.event_type_distribution.length" class="muted">暂无数据</p>
      </div>

      <div class="panel stack">
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

    <div class="dashboard-grid-wide">
      <div class="panel stack">
        <div class="section-title">
          <h2>最近事件</h2>
          <RouterLink class="button secondary" to="/events">查看事件库</RouterLink>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>事件</th>
                <th>风险</th>
                <th>类型</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="event in data.recent_events" :key="event.event_id">
                <td>
                  <RouterLink :to="`/events/${event.event_id}`">
                    <strong>{{ event.title }}</strong>
                  </RouterLink>
                  <p class="muted small">{{ event.summary }}</p>
                </td>
                <td>
                  <RiskBadge :level="effectiveRiskLevel(event)" />
                  <p class="muted small">{{ riskScoreText(event.risk_score) }}</p>
                </td>
                <td>{{ event.event_type || '未知' }}</td>
                <td class="muted small">{{ event.updated_at }}</td>
              </tr>
              <tr v-if="!data.recent_events.length">
                <td colspan="4" class="muted">暂无事件</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel stack">
        <div class="section-title">
          <h2>最近复核</h2>
          <span class="muted small">处置闭环</span>
        </div>
        <div v-for="item in data.recent_reviews" :key="item.id" class="metric">
          <span>{{ item.created_at }}</span>
          <strong>{{ item.action_type }}</strong>
          <p class="muted small">{{ item.comment || item.event_id }}</p>
        </div>
        <p v-if="!data.recent_reviews.length" class="muted">暂无复核记录</p>
      </div>
    </div>
  </template>
</template>
