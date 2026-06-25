<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listAuditLogs, type AuditLog } from '../../api/audit'
import { errorMessage } from './helpers'

const emit = defineEmits<{
  error: [message: string]
}>()

const logs = ref<AuditLog[]>([])
const total = ref(0)
const loading = ref(false)
const filterAction = ref('')
const filterActor = ref('')
const filterDateFrom = ref('')
const filterDateTo = ref('')
const page = ref(1)

async function load(): Promise<void> {
  loading.value = true
  try {
    const params: Record<string, unknown> = { page: page.value, page_size: 50 }
    if (filterAction.value) params.action = filterAction.value
    if (filterActor.value) params.actor = filterActor.value
    if (filterDateFrom.value) params.date_from = filterDateFrom.value
    if (filterDateTo.value) params.date_to = filterDateTo.value
    const data = await listAuditLogs(params)
    logs.value = [...data.items]
    total.value = data.total
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载审计日志失败'))
  } finally {
    loading.value = false
  }
}

function search(): void {
  page.value = 1
  void load()
}

function prevPage(): void {
  page.value -= 1
  void load()
}

function nextPage(): void {
  page.value += 1
  void load()
}

onMounted(load)
</script>

<template>
  <section class="settings-section">
    <div class="settings-filterbar">
      <select v-model="filterAction" class="select">
        <option value="">全部动作</option>
        <option value="settings.update">设置更新</option>
        <option value="risk_rules.update">规则更新</option>
        <option value="model_service">模型服务</option>
        <option value="notification">通知渠道</option>
        <option value="data_management.cleanup">数据清理</option>
      </select>
      <input v-model="filterActor" class="input" placeholder="操作人" />
      <input v-model="filterDateFrom" class="input" type="date" />
      <input v-model="filterDateTo" class="input" type="date" />
      <button class="button" :disabled="loading" @click="search">查询</button>
    </div>
    <div class="table-wrap">
      <table>
        <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>资源</th><th>详情</th></tr></thead>
        <tbody>
          <tr v-for="row in logs" :key="row.id">
            <td class="small muted">{{ row.created_at }}</td>
            <td>{{ row.actor }} / {{ row.role }}</td>
            <td>{{ row.action }}</td>
            <td>{{ row.resource_type }} {{ row.resource_id || '' }}</td>
            <td class="small muted">{{ JSON.stringify(row.detail || {}) }}</td>
          </tr>
          <tr v-if="!logs.length">
            <td colspan="5" class="muted">{{ loading ? '加载中...' : '暂无审计日志' }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <span class="muted small">共 {{ total }} 条</span>
      <button class="button secondary pager-button" :disabled="page <= 1" @click="prevPage">上一页</button>
      <span class="page-number">{{ page }}</span>
      <button class="button secondary pager-button" :disabled="page * 50 >= total" @click="nextPage">下一页</button>
    </div>
  </section>
</template>
