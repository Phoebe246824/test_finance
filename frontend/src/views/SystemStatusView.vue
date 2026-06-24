<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  getHealth,
  getHardware,
  getRuntime,
  type HardwareResponse,
  type HealthResponse,
  type RuntimeResponse,
} from '../api/system'

type HardwareValue = boolean | number | readonly string[] | string | null | undefined
type HardwareEntry = readonly [string, HardwareValue]
type HardwareField = readonly [string, string]
type ServiceKey = keyof HealthResponse

const health = ref<Partial<HealthResponse>>({})
const hardware = ref<HardwareResponse>({})
const runtime = ref<Partial<RuntimeResponse>>({})
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [healthData, hardwareData, runtimeData] = await Promise.all([
      getHealth(),
      getHardware(),
      getRuntime(),
    ])
    health.value = healthData
    hardware.value = hardwareData
    runtime.value = runtimeData
  } finally {
    loading.value = false
  }
}

function formatValue(value: HardwareValue) {
  if (Array.isArray(value)) return value.length ? value.join(', ') : '无'
  if (typeof value === 'boolean') return value ? '正常' : '异常'
  if (value === null || value === undefined || value === '') return '未检测到'
  return String(value)
}

const serviceCards = computed(() => {
  const source = health.value || {}
  const labels: Record<ServiceKey, string> = {
    api: 'API 服务',
    milvus: 'Milvus',
    neo4j: 'Neo4j',
    llm: 'LLM 服务',
  }
  const keys: readonly ServiceKey[] = ['api', 'milvus', 'neo4j', 'llm']
  return keys.map((key) => {
    const value = source[key]
    return {
      key,
      name: labels[key],
      ok: Boolean(value?.ok),
      detail: value?.detail || '',
    }
  })
})

const hardwareItems = computed(() => {
  const preferred: readonly HardwareField[] = [
    ['cpu', 'CPU'],
    ['memory', '内存'],
    ['gpu', 'GPU'],
    ['disk', '硬盘'],
    ['system', '系统'],
  ]
  const entries = preferred
    .map(([field, label]): HardwareEntry => [label, hardware.value[field] ?? hardware.value[label]])
    .filter((entry): entry is HardwareEntry => {
      const value = entry[1]
      return value !== undefined && value !== null && value !== ''
    })
  return entries.length ? entries : Object.entries(hardware.value)
})

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>系统状态</h1>
      <p>查看 Milvus 运行存储、图谱服务和设备信息。</p>
    </div>
  </section>

  <div class="system-layout">
    <div class="system-service-grid">
      <div v-for="item in serviceCards" :key="item.key" class="metric service-card">
        <span>{{ item.name }}</span>
        <strong :class="item.ok ? 'success-text' : 'danger-text'">
          {{ item.ok ? '正常' : '异常' }}
        </strong>
        <em>{{ item.detail || '未检测到' }}</em>
      </div>
    </div>

    <div class="grid-2">
      <div class="panel stack">
        <h2>运行指标</h2>
        <div class="metric">
          <span>存储后端</span>
          <strong>{{ runtime.storage_backend || 'milvus' }}</strong>
        </div>
        <div class="metric">
          <span>事件总数</span>
          <strong>{{ runtime.event_count ?? 0 }}</strong>
        </div>
        <div class="metric">
          <span>复核动作</span>
          <strong>{{ runtime.review_count ?? 0 }}</strong>
        </div>
        <div class="metric">
          <span>黑名单条目</span>
          <strong>{{ runtime.blacklist_count ?? 0 }}</strong>
        </div>
        <div class="metric">
          <span>运行时长</span>
          <strong>{{ runtime.uptime_seconds ?? 0 }} 秒</strong>
        </div>
      </div>

      <div class="panel stack">
        <h2>硬件信息</h2>
        <div class="metric" v-for="[key, value] in hardwareItems" :key="key">
          <span>{{ key }}</span>
          <strong>{{ formatValue(value) }}</strong>
        </div>
      </div>
    </div>
  </div>
</template>
