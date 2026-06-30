<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { expandGraphNode, searchPersonGraph } from '../api/events'
import GraphViewer from '../components/GraphViewer.vue'
import { useWorkbenchStore } from '../stores/workbench'
import { normalizeGraphData } from '../utils/graph'

const store = useWorkbenchStore()
const keyword = computed({
  get: () => store.personKeyword,
  set: (value) => {
    store.personKeyword = value
  },
})
const loading = ref(false)
const error = ref('')
const status = ref('请输入客户编号或姓名后搜索')
const graph = ref<{ nodes: any[]; edges: any[]; source?: string }>({ nodes: [], edges: [] })
const SEARCH_TIMEOUT_MS = 25000
let searchToken = 0
let searchController: AbortController | null = null
const graphVersion = ref(0)
const graphKey = computed(() => `person-graph-${graphVersion.value}`)

onMounted(() => {
  if ((store.personGraph.nodes || []).length) {
    setGraph(store.personGraph)
    const kw = store.personKeyword
    status.value = kw
      ? `已搜索 ${kw}，返回 ${store.personGraph.nodes.length} 个节点`
      : `图谱已恢复，共 ${store.personGraph.nodes.length} 个节点`
  }
})

async function search() {
  if (!keyword.value.trim()) return
  const term = keyword.value.trim()
  searchController?.abort()
  searchController = new AbortController()
  loading.value = true
  error.value = ''
  status.value = '正在搜索图谱...'
  setGraph({ nodes: [], edges: [] })
  const currentToken = ++searchToken
  const timeoutId = window.setTimeout(() => {
    if (currentToken !== searchToken) return
    searchController?.abort()
    loading.value = false
    error.value = '搜索超时，请重试'
    status.value = '搜索超时'
  }, SEARCH_TIMEOUT_MS)
  try {
    const nextGraph = await searchPersonGraph(term, searchController.signal)
    if (currentToken !== searchToken) return
    const normalized = normalizeGraphData(nextGraph)
    store.setPersonGraph(term, normalized)
    await Promise.resolve()
    if (currentToken !== searchToken) return
    setGraph(normalized)
    if (!(normalized.nodes || []).length) {
      status.value = `已搜索 ${term}，结果为空`
    } else {
      status.value = `已搜索 ${term}，返回 ${normalized.nodes.length} 个节点`
    }
  } catch (err: any) {
    if (currentToken !== searchToken) return
    if (err?.name === 'CanceledError' || err?.name === 'AbortError') return
    if (!loading.value && error.value === '搜索超时，请重试') return
    error.value = err?.response?.data?.detail || err?.message || '搜索失败'
    status.value = '搜索失败'
  } finally {
    if (currentToken === searchToken) {
      loading.value = false
    }
    window.clearTimeout(timeoutId)
  }
}

async function expand(node: any) {
  const nodeId = node.properties?.id_number || node.id || node.neo4j_element_id
  if (!nodeId) return
  try {
    const expanded = normalizeGraphData(await expandGraphNode(nodeId))
    store.mergePersonGraph(expanded)
    setGraph(store.personGraph)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '扩展节点失败'
  }
}

function setGraph(nextGraph: { nodes?: any[]; edges?: any[]; source?: string }) {
  const normalized = normalizeGraphData(nextGraph)
  graph.value = {
    nodes: normalized.nodes,
    edges: normalized.edges,
    source: normalized.source,
  }
  graphVersion.value += 1
}
</script>

<template>
  <section class="page-header">
    <div>
      <h1>人物图谱</h1>
      <p>搜索客户编号或姓名，查看与该主体相关的客户、账户、商户、设备和风险信号。</p>
    </div>
  </section>

  <div class="panel stack">
    <div class="graph-searchbar">
      <label class="search-field graph-search-field">
        <input
          v-model="keyword"
          class="input"
          placeholder="例如 P101、客户A、客户B"
          @keyup.enter="search"
        />
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" />
        </svg>
      </label>
      <button class="button" :disabled="loading" @click="search">
        {{ loading ? '搜索中...' : '搜索图谱' }}
      </button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <p class="muted small">{{ status }}</p>
    <p class="muted small">点击节点或边可查看 Neo4j 属性；点击节点详情里的“扩展关联节点”可继续展开。</p>
    <GraphViewer
      :key="graphKey"
      :nodes="graph.nodes"
      :edges="graph.edges"
      expandable
      @expand="expand"
    />
  </div>
</template>
