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

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await listEvents({
      page: page.value,
      page_size: pageSize,
      keyword: keyword.value || undefined,
      risk_level: riskLevel.value || undefined,
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
    <div class="toolbar">
      <input v-model="keyword" class="input" placeholder="搜索客户、账户、摘要" />
      <select v-model="riskLevel" class="select">
        <option value="">全部风险</option>
        <option value="high">高风险</option>
        <option value="medium">中风险</option>
        <option value="low">低风险</option>
      </select>
      <button class="button secondary" :disabled="loading" @click="search">查询</button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <p class="muted small">共 {{ total }} 条</p>

    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>事件</th>
            <th>风险</th>
            <th>状态</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in events" :key="item.event_id">
            <td>
              <RouterLink :to="`/events/${item.event_id}`">
                <strong>{{ eventTitle(item) }}</strong>
              </RouterLink>
              <p class="muted small">{{ eventSummary(item) }}</p>
            </td>
            <td>
              <RiskBadge :level="effectiveRiskLevel(item)" />
              <div class="small muted">{{ riskScoreText(item.risk_score) }}</div>
            </td>
            <td>{{ item.status }}</td>
            <td class="small muted">{{ item.updated_at }}</td>
            <td>
              <button class="button danger" @click="remove(item.event_id)">删除</button>
            </td>
          </tr>
          <tr v-if="!events.length">
            <td colspan="5" class="muted">暂无事件</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <button class="button secondary" :disabled="loading || page <= 1" @click="prevPage">上一页</button>
      <span class="muted small">第 {{ page }} / {{ totalPages() }} 页，每页 {{ pageSize }} 条</span>
      <button class="button secondary" :disabled="loading || page >= totalPages()" @click="nextPage">下一页</button>
    </div>
  </div>
</template>
