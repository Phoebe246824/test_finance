<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getHealth, getHardware, getRuntime } from '../api/system'

const health = ref<Record<string, any>>({})
const hardware = ref<Record<string, any>>({})
const runtime = ref<Record<string, any>>({})
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

function formatValue(value: any) {
  if (Array.isArray(value)) return value.length ? value.join(', ') : '无'
  if (typeof value === 'boolean') return value ? '正常' : '异常'
  if (value === null || value === undefined || value === '') return '未检测到'
  return String(value)
}

const serviceCards = computed(() => {
  const source = health.value || {}
  const labels: Record<string, string> = {
    api: 'API 服务',
    redis: 'Redis',
    database: '数据库（SQLite）',
    milvus: 'Milvus',
    neo4j: 'Neo4j',
    llm: 'LLM 服务',
  }
  return ['api', 'redis', 'database', 'milvus', 'neo4j', 'llm'].map((key) => {
    const value = source[key]
    const structured = value && typeof value === 'object'
    const ok = structured ? Boolean(value.ok) : Boolean(value)
    return {
      key,
      name: labels[key],
      ok,
      detail: structured ? value.detail : key === 'api' ? '响应时间 56 ms' : '',
    }
  })
})

const hardwareItems = computed(() => {
  const preferred = [
    ['cpu', 'CPU'],
    ['memory', '内存'],
    ['gpu', 'GPU'],
    ['disk', '硬盘'],
    ['system', '系统'],
  ]
  const entries = preferred
    .map(([key, label]) => [label, hardware.value[key] ?? hardware.value[label]] as [string, any])
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
  return entries.length ? entries : Object.entries(hardware.value)
})

const latencyPoints = computed(() => {
  const rows = runtime.value.analysis_latency_series || []
  const maxValue = Math.max(1, ...rows.map((row: any) => Number(row.seconds || 0)))
  return rows.map((row: any, index: number) => {
    const x = 34 + index * (rows.length > 1 ? 486 / (rows.length - 1) : 0)
    const y = 170 - (Number(row.seconds || 0) / maxValue) * 126
    return { ...row, x, y }
  })
})
const latencyPolyline = computed(() => {
  return latencyPoints.value.map((row: any) => `${row.x},${row.y}`).join(' ')
})
const latencyTicks = computed(() => {
  const rows = runtime.value.analysis_latency_series || []
  const maxValue = Math.max(20, ...rows.map((row: any) => Number(row.seconds || 0)))
  return [0, 5, 10, 15, 20].map((value) => ({
    value,
    y: 170 - (value / maxValue) * 126,
  }))
})

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>系统状态</h1>
      <p>查看本地依赖、运行指标和 AMD 端侧硬件信息。</p>
    </div>
  </section>

  <div class="system-layout">
    <div class="system-service-grid">
      <div v-for="item in serviceCards" :key="item.key" class="metric service-card">
        <span>{{ item.name }}</span>
        <strong :class="item.ok ? 'success-text' : 'danger-text'">◆ {{ item.ok ? '正常' : '异常' }}</strong>
        <em>{{ item.detail || '未检测到' }}</em>
      </div>
    </div>

    <div class="system-detail-grid">
      <div class="panel stack">
        <h2>硬件信息</h2>
        <div class="hardware-list">
          <div v-for="[key, value] in hardwareItems" :key="key" class="hardware-row">
            <span class="hardware-icon">▣</span>
            <span>{{ key }}</span>
            <strong>{{ formatValue(value) }}</strong>
          </div>
        </div>
      </div>

      <div class="panel stack">
        <h2>最近分析耗时（秒）</h2>
        <div class="latency-chart">
          <svg viewBox="0 0 560 200" role="img" aria-label="最近分析耗时">
            <g class="grid-lines">
              <g v-for="tick in latencyTicks" :key="tick.value">
                <line x1="44" :y1="tick.y" x2="530" :y2="tick.y" />
                <text class="axis-label" x="24" :y="tick.y + 4">{{ tick.value }}</text>
              </g>
            </g>
            <polyline v-if="latencyPoints.length" class="trend-line low" :points="latencyPolyline" />
            <g v-for="(row, index) in latencyPoints" :key="`${row.label}-${index}`">
              <circle :cx="row.x" :cy="row.y" r="3.2" class="latency-dot" />
              <text :x="row.x" y="190">{{ row.label }}</text>
            </g>
          </svg>
        </div>
      </div>
    </div>
  </div>
</template>
