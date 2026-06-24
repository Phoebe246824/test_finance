<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listAuditLogs, type AuditLog } from '../api/audit'

const logs = ref<AuditLog[]>([])
const total = ref(0)
const error = ref('')
const loading = ref(false)

function errorMessage(err: unknown, fallback: string) {
  if (err && typeof err === 'object') {
    const response = 'response' in err ? err.response : undefined
    if (response && typeof response === 'object' && 'data' in response) {
      const data = response.data
      if (data && typeof data === 'object' && 'detail' in data) {
        const detail = data.detail
        if (typeof detail === 'string' && detail) return detail
      }
    }
    if ('message' in err && typeof err.message === 'string' && err.message) {
      return err.message
    }
  }
  return fallback
}

async function load() {
  loading.value = true
  error.value = ''
  try {
    const data = await listAuditLogs({ page_size: 100 })
    logs.value = [...data.items]
    total.value = data.total
  } catch (err: unknown) {
    error.value = errorMessage(err, '加载审计日志失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>审计日志</h1>
      <p>查看黑名单、风险规则、事件删除和人工复核等关键操作。</p>
    </div>
    <button class="button secondary" :disabled="loading" @click="load">刷新</button>
  </section>

  <div class="panel stack">
    <div v-if="error" class="error">{{ error }}</div>
    <p class="muted small">共 {{ total }} 条</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>时间</th>
            <th>操作人</th>
            <th>动作</th>
            <th>资源</th>
            <th>详情</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="item in logs" :key="item.id">
            <td class="small muted">{{ item.created_at }}</td>
            <td>{{ item.actor }} / {{ item.role }}</td>
            <td>{{ item.action }}</td>
            <td>{{ item.resource_type }} {{ item.resource_id || '' }}</td>
            <td class="small muted">{{ JSON.stringify(item.detail || {}) }}</td>
          </tr>
          <tr v-if="!logs.length">
            <td colspan="5" class="muted">暂无审计日志</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
