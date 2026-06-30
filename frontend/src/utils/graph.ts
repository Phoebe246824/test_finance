export type GraphData = {
  nodes: any[]
  edges: any[]
  source?: string
}

export function normalizeGraphData(graph: { nodes?: any[]; edges?: any[]; source?: string } | null | undefined): GraphData {
  const nodes = (graph?.nodes || [])
    .map((node, index) => {
      const id = String(node?.id || node?.neo4j_element_id || node?.properties?.elementId || `node-${index}`)
      return { ...node, id }
    })
    .filter((node) => node.id)
  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges = (graph?.edges || [])
    .map((edge, index) => ({
      ...edge,
      source: String(edge?.source || ''),
      target: String(edge?.target || ''),
      id: edge?.id || edge?.neo4j_element_id || `${edge?.source}-${edge?.target}-${edge?.type || edge?.label || index}`,
    }))
    .filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
  return { nodes, edges, source: graph?.source }
}

export function hasGraphData(graph: { nodes?: any[]; edges?: any[] } | null | undefined) {
  return Boolean((graph?.nodes || []).length || (graph?.edges || []).length)
}
