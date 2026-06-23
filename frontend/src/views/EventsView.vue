<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { listEvents, deleteEvent } from '../api/events'
import RiskBadge from '../components/RiskBadge.vue'
import { effectiveRiskLevel, riskScoreText } from '../utils/risk'

const events = ref<any[]>([])
const total = ref(0)
const keyword = ref('')
const riskLevel = ref('')
const dateFrom = ref('')
const dateTo = ref('')
const loading = ref(false)
const error = ref('')
const page = ref(1)
const pageSize = 10

function eventTitle(item: any) {
  const explicitTitle = String(item.title || '').trim()
  if (explicitTitle && explicitTitle !== item.event_id) return explicitTitle

  const text = String(item.summary || item.raw_content || '').trim()
  if (!text) return `事件 ${String(item.event_id || '').slice(0, 8)}`

  const normalized = text
    .replace(/^["“”]+|["“”]+$/g, '')
    .replace(/^\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}[，,、\s]*/, '')
    .replace(/【([^#】]+)#\s*([^】]+)】/g, '$2')
    .trim()

  return normalized.length > 28 ? `${normalized.slice(0, 28)}...` : normalized
}

function eventSummary(item: any) {
  const text = String(item.summary || item.raw_content || '').trim()
  return text.length > 96 ? `${text.slice(0, 96)}...` : text
}

function hitType(item: any) {
  const parts = []
  if (item.matched_persons?.length) parts.push('人员')
  if (item.matched_keywords?.length) parts.push('关键词')
  if (item.event_similarity?.hit) parts.push('相似事件')
  return parts.length ? parts.join('、') : item.blacklist_decision || '-'
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await listEvents({
      page: page.value,
      page_size: pageSize,
      keyword: keyword.value || undefined,
      risk_level: riskLevel.value || undefined,
      date_from: dateFrom.value || undefined,
      date_to: dateTo.value || undefined,
    })
    events.value = data.items || []
    total.value = data.total || 0
  } catch (err: any) {
    error.value = err?.message || '加载事件失败'
  } finally {
    loading.value = false
  }
}

function totalPages() {
  return Math.max(1, Math.ceil(total.value / pageSize))
}

async function search() {
  page.value = 1
  await load()
}

async function prevPage() {
  if (page.value <= 1) return
  page.value -= 1
  await load()
}

async function nextPage() {
  if (page.value >= totalPages()) return
  page.value += 1
  await load()
}

async function remove(eventId: string) {
  await deleteEvent(eventId)
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>事件库</h1>
      <p>查看已分析或暂存的金融风险事件。</p>
    </div>
    <RouterLink class="button" to="/analysis">新增分析</RouterLink>
  </section>

  <div class="panel stack">
    <div class="prototype-filterbar">
      <label class="search-field event-search-field">
        <input v-model="keyword" class="input" placeholder="请输入关键词" @keyup.enter="search" />
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" />
        </svg>
      </label>
      <select v-model="riskLevel" class="select">
        <option value="">风险等级：全部</option>
        <option value="high">高风险</option>
        <option value="medium">中风险</option>
        <option value="low">低风险</option>
      </select>
      <label class="date-range-field">
        <span>时间范围：</span>
        <input v-model="dateFrom" type="date" title="开始日期" @change="search" />
        <em>~</em>
        <input v-model="dateTo" type="date" title="结束日期" @change="search" />
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v3m10-3v3M4 9h16M5 5h14v16H5z" /></svg>
      </label>
      <button class="button" :disabled="loading" @click="search">搜索</button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>事件ID</th>
            <th>标题</th>
            <th>风险等级</th>
            <th>风险分数</th>
            <th>命中类型</th>
            <th>状态</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in events" :key="item.event_id">
            <td class="small">{{ item.event_id }}</td>
            <td>
              <strong>{{ eventTitle(item) }}</strong>
              <p class="muted small">{{ eventSummary(item) }}</p>
            </td>
            <td>
              <RiskBadge :level="effectiveRiskLevel(item)" />
            </td>
            <td>{{ riskScoreText(item.risk_score) }}</td>
            <td>{{ hitType(item) }}</td>
            <td>{{ item.status }}</td>
            <td class="small muted">{{ item.updated_at }}</td>
            <td>
              <div class="table-actions">
                <RouterLink class="table-action" :to="`/events/${item.event_id}`">查看</RouterLink>
                <button class="link-danger" @click="remove(item.event_id)">删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!events.length">
            <td colspan="8" class="muted">暂无事件</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <span class="muted small">共 {{ total }} 条</span>
      <button class="button secondary pager-button" :disabled="loading || page <= 1" @click="prevPage">‹</button>
      <span class="page-number">{{ page }}</span>
      <button class="button secondary pager-button" :disabled="loading || page >= totalPages()" @click="nextPage">›</button>
      <span class="muted small">10 条/页</span>
    </div>
  </div>
</template>
