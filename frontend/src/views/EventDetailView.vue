<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'
import { expandGraphNode, getEvent, getEventGraph } from '../api/events'
import RiskBadge from '../components/RiskBadge.vue'
import BlacklistHitPanel from '../components/BlacklistHitPanel.vue'
import DimensionScoreBars from '../components/DimensionScoreBars.vue'
import GraphViewer from '../components/GraphViewer.vue'
import TrendReportPanel from '../components/TrendReportPanel.vue'
import ReviewActionPanel from '../components/ReviewActionPanel.vue'
import { useWorkbenchStore } from '../stores/workbench'
import { effectiveRiskLevel, riskRuleText, riskScoreText } from '../utils/risk'

const route = useRoute()
const store = useWorkbenchStore()
const event = ref<any>(null)
const graph = ref<{ nodes: any[]; edges: any[]; source?: string }>({ nodes: [], edges: [] })
const error = ref('')

async function load() {
  const eventId = String(route.params.eventId)
  try {
    event.value = await getEvent(eventId)
    graph.value = store.eventGraphs[eventId] || await getEventGraph(eventId)
    store.setEventGraph(eventId, graph.value)
  } catch (err: any) {
    error.value = err?.message || '加载详情失败'
  }
}

async function expand(node: any) {
  const nodeId = node.properties?.id_number || node.id || node.neo4j_element_id
  if (!nodeId) return
  const expanded = await expandGraphNode(nodeId)
  const nodes = new Map(graph.value.nodes.map((item) => [item.id, item]))
  const edges = new Map(graph.value.edges.map((item) => [item.id || `${item.source}-${item.target}-${item.label}`, item]))
  for (const item of expanded.nodes || []) nodes.set(item.id, item)
  for (const item of expanded.edges || []) edges.set(item.id || `${item.source}-${item.target}-${item.label}`, item)
  graph.value = { nodes: Array.from(nodes.values()), edges: Array.from(edges.values()), source: expanded.source }
  store.setEventGraph(String(route.params.eventId), graph.value)
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>事件详情</h1>
      <p>{{ route.params.eventId }}</p>
    </div>
    <RouterLink class="button secondary" to="/events">返回事件库</RouterLink>
  </section>

  <div v-if="error" class="error">{{ error }}</div>
  <div v-if="event" class="stack">
    <div class="grid-3">
      <div class="metric">
        <span>风险等级</span>
        <RiskBadge :level="effectiveRiskLevel(event)" />
      </div>
      <div class="metric">
        <span>风险分数</span>
        <strong>{{ riskScoreText(event.risk_score) }}</strong>
      </div>
      <div class="metric">
        <span>事件类型</span>
        <strong>{{ event.event_type || '未知' }}</strong>
      </div>
    </div>

    <div class="grid-main-side">
      <div class="panel stack">
        <h2>关系图谱</h2>
        <GraphViewer :nodes="graph.nodes" :edges="graph.edges" expandable tall @expand="expand" />
      </div>
      <BlacklistHitPanel
        :blacklist="{
          decision: event.blacklist_decision,
          matched_persons: event.matched_persons,
          matched_keywords: event.matched_keywords,
          event_similarity: event.event_similarity,
        }"
      />
    </div>

    <div class="grid-2">
      <div class="panel stack">
        <h2>事件原文</h2>
        <p class="pre-wrap">{{ event.raw_content }}</p>
      </div>
      <div class="panel stack">
        <h2>评估说明</h2>
        <p class="muted small">{{ riskRuleText() }}</p>
        <p class="pre-wrap">{{ event.reasoning || '暂无说明' }}</p>
        <DimensionScoreBars :scores="event.dimension_scores" />
      </div>
    </div>

    <TrendReportPanel :report="event.trend_report" />
    <ReviewActionPanel :event-id="event.event_id" :actions="event.review_actions" @saved="load" />
  </div>
</template>
