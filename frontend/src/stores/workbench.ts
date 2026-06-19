import { defineStore } from 'pinia'

type GraphData = {
  nodes: any[]
  edges: any[]
  source?: string
}

const defaultText = `2026年6月14日 23:48，【P102# 客户B】再次通过手机银行向4个新开户账户分散转出 196000 元，随后其中两个收款账户在10分钟内继续转入同一虚拟币平台商户【M301# 虚拟币商户】。交易行为疑似分拆交易与洗钱资金归集，反洗钱系统要求立即复核并冻结后续出金。`

export const useWorkbenchStore = defineStore('workbench', {
  state: () => ({
    analysisText: defaultText,
    analysisResult: null as any,
    eventGraphs: {} as Record<string, GraphData>,
    personKeyword: '',
    personGraph: { nodes: [], edges: [] } as GraphData,
  }),
  actions: {
    setAnalysisResult(result: any) {
      this.analysisResult = result
    },
    setEventGraph(eventId: string, graph: GraphData) {
      this.eventGraphs[eventId] = graph
    },
    setPersonGraph(keyword: string, graph: GraphData) {
      this.personKeyword = keyword
      this.personGraph = graph
    },
    mergePersonGraph(graph: GraphData) {
      const nodes = new Map(this.personGraph.nodes.map((node) => [node.id, node]))
      const edges = new Map(this.personGraph.edges.map((edge) => [edge.id || `${edge.source}-${edge.target}-${edge.label}`, edge]))
      for (const node of graph.nodes || []) nodes.set(node.id, node)
      for (const edge of graph.edges || []) edges.set(edge.id || `${edge.source}-${edge.target}-${edge.label}`, edge)
      this.personGraph = {
        nodes: Array.from(nodes.values()),
        edges: Array.from(edges.values()),
        source: graph.source || this.personGraph.source,
      }
    },
  },
})
