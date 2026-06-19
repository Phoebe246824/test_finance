<script setup lang="ts">
import { computed, ref } from 'vue'
import { expandGraphNode, searchPersonGraph } from '../api/events'
import GraphViewer from '../components/GraphViewer.vue'
import { useWorkbenchStore } from '../stores/workbench'

const store = useWorkbenchStore()
const keyword = computed({
  get: () => store.personKeyword,
  set: (value) => {
    store.personKeyword = value
  },
})
const loading = ref(false)
const error = ref('')

async function search() {
  if (!keyword.value.trim()) return
  loading.value = true
  error.value = ''
  try {
    store.setPersonGraph(keyword.value.trim(), await searchPersonGraph(keyword.value.trim()))
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '搜索失败'
  } finally {
    loading.value = false
  }
}

async function expand(node: any) {
  const nodeId = node.properties?.id_number || node.id || node.neo4j_element_id
  if (!nodeId) return
  try {
    store.mergePersonGraph(await expandGraphNode(nodeId))
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '扩展节点失败'
  }
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
    <div class="toolbar">
      <input
        v-model="keyword"
        class="input"
        placeholder="例如 P101、客户A、客户B"
        @keyup.enter="search"
      />
      <button class="button" :disabled="loading" @click="search">
        {{ loading ? '搜索中...' : '搜索图谱' }}
      </button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <p class="muted small">点击节点或边可查看 Neo4j 属性；点击节点详情里的“扩展关联节点”可继续展开。</p>
    <GraphViewer
      :nodes="store.personGraph.nodes"
      :edges="store.personGraph.edges"
      expandable
      @expand="expand"
    />
  </div>
</template>
