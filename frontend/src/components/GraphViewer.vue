<script setup lang="ts">
import { computed, ref, watch } from 'vue'

type NodeItem = {
  id: string
  label: string
  type: string
  labels?: string[]
  properties?: Record<string, any>
}

type EdgeItem = {
  id?: string
  source: string
  target: string
  label?: string
  type?: string
  properties?: Record<string, any>
}

const props = withDefaults(
  defineProps<{
    nodes: NodeItem[]
    edges: EdgeItem[]
    expandable?: boolean
    tall?: boolean
  }>(),
  { expandable: false, tall: false },
)

const emit = defineEmits<{ expand: [node: NodeItem] }>()

const selected = ref<{ kind: 'node' | 'edge'; data: any } | null>(null)
const detailOpen = ref(true)
const zoom = ref(1)
const pan = ref({ x: 0, y: 0 })
const dragging = ref(false)
const dragStart = ref({ x: 0, y: 0, px: 0, py: 0 })
const nodeDrag = ref<{ id: string; dx: number; dy: number } | null>(null)
const manualPositions = ref<Record<string, { x: number; y: number }>>({})
const fullscreen = ref(false)

const palette: Record<string, string> = {
  Customer: '#c9445a',
  Account: '#7b61b3',
  Merchant: '#2c9b72',
  Device: '#2f84c7',
  RiskSignal: '#d98a28',
  RiskEvent: '#2383d1',
  Episodic: '#607085',
  Entity: '#0f5f91',
}

const typeLabels: Record<string, string> = {
  Customer: '客户',
  Account: '账户',
  Merchant: '商户/机构',
  Device: '设备',
  RiskSignal: '风险信号',
  RiskEvent: '事件',
  Entity: '实体',
}

const layout = computed(() => {
  const width = 1280
  const height = props.tall ? 760 : 620
  const nodeIds = new Set(props.nodes.map((node) => node.id))
  const validEdges = props.edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target))
  const positions: Record<string, { x: number; y: number }> = {}
  const velocities: Record<string, { x: number; y: number }> = {}
  const center = { x: width / 2, y: height / 2 }
  const typeOffsets: Record<string, { x: number; y: number }> = {
    Customer: { x: -180, y: -80 },
    Account: { x: -250, y: 130 },
    Merchant: { x: 220, y: 100 },
    Device: { x: 40, y: 210 },
    RiskSignal: { x: 250, y: -120 },
    RiskEvent: { x: 0, y: 0 },
  }

  props.nodes.forEach((node, index) => {
    const angle = (index * 2.3999632297) % (Math.PI * 2)
    const radius = 80 + 34 * Math.sqrt(index)
    const offset = typeOffsets[normalizedType(node)] || { x: 0, y: 0 }
    const generated = {
      x: center.x + offset.x + Math.cos(angle) * radius,
      y: center.y + offset.y + Math.sin(angle) * radius,
    }
    positions[node.id] = manualPositions.value[node.id] || generated
    velocities[node.id] = { x: 0, y: 0 }
  })

  for (let tick = 0; tick < 130; tick += 1) {
    for (let i = 0; i < props.nodes.length; i += 1) {
      for (let j = i + 1; j < props.nodes.length; j += 1) {
        const a = props.nodes[i]
        const b = props.nodes[j]
        const pa = positions[a.id]
        const pb = positions[b.id]
        let dx = pa.x - pb.x
        let dy = pa.y - pb.y
        const distance = Math.max(24, Math.sqrt(dx * dx + dy * dy))
        const force = 1550 / (distance * distance)
        dx /= distance
        dy /= distance
        velocities[a.id].x += dx * force
        velocities[a.id].y += dy * force
        velocities[b.id].x -= dx * force
        velocities[b.id].y -= dy * force
      }
    }

    for (const edge of validEdges) {
      const source = positions[edge.source]
      const target = positions[edge.target]
      const dx = target.x - source.x
      const dy = target.y - source.y
      const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy))
      const preferred = 155
      const force = (distance - preferred) * 0.008
      const fx = (dx / distance) * force
      const fy = (dy / distance) * force
      velocities[edge.source].x += fx
      velocities[edge.source].y += fy
      velocities[edge.target].x -= fx
      velocities[edge.target].y -= fy
    }

    for (const node of props.nodes) {
      if (manualPositions.value[node.id]) continue
      const p = positions[node.id]
      const v = velocities[node.id]
      v.x += (center.x - p.x) * 0.002
      v.y += (center.y - p.y) * 0.002
      p.x = Math.max(42, Math.min(width - 42, p.x + v.x))
      p.y = Math.max(42, Math.min(height - 42, p.y + v.y))
      v.x *= 0.82
      v.y *= 0.82
    }
  }

  const edgeGroups = new Map<string, EdgeItem[]>()
  for (const edge of validEdges) {
    const endpoints = [edge.source, edge.target].sort()
    const key = `${endpoints[0]}::${endpoints[1]}`
    edgeGroups.set(key, [...(edgeGroups.get(key) || []), edge])
  }

  const edges = validEdges.map((edge) => {
    const source = positions[edge.source]
    const target = positions[edge.target]
    const endpoints = [edge.source, edge.target].sort()
    const siblings = edgeGroups.get(`${endpoints[0]}::${endpoints[1]}`) || [edge]
    const siblingIndex = siblings.indexOf(edge)
    const offset = (siblingIndex - (siblings.length - 1) / 2) * 34
    const dx = target.x - source.x
    const dy = target.y - source.y
    const distance = Math.max(1, Math.sqrt(dx * dx + dy * dy))
    const ux = dx / distance
    const uy = dy / distance
    const nx = -uy
    const ny = ux
    const sourceNode = props.nodes.find((node) => node.id === edge.source)
    const targetNode = props.nodes.find((node) => node.id === edge.target)
    const sourceRadius = sourceNode ? nodeRadius(sourceNode) + 7 : 24
    const targetRadius = targetNode ? nodeRadius(targetNode) + 11 : 28
    const x1 = source.x + ux * sourceRadius
    const y1 = source.y + uy * sourceRadius
    const x2 = target.x - ux * targetRadius
    const y2 = target.y - uy * targetRadius
    const cx = (x1 + x2) / 2 + nx * offset
    const cy = (y1 + y2) / 2 + ny * offset
    const path = Math.abs(offset) < 1
      ? `M ${x1} ${y1} L ${x2} ${y2}`
      : `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`
    return {
      ...edge,
      path,
      labelX: cx,
      labelY: cy - 7,
    }
  })

  return { width, height, positions, edges }
})

const graphClass = computed(() => ({
  'graph-miro': true,
  'graph-miro-fullscreen': fullscreen.value,
  'graph-miro-detail-closed': !detailOpen.value,
  tall: props.tall,
}))

const viewTransform = computed(() => `translate(${pan.value.x} ${pan.value.y}) scale(${zoom.value})`)

const legend = computed(() => {
  const types = Array.from(new Set(props.nodes.map((node) => normalizedType(node))))
  return types.map((type) => ({
    type,
    label: typeLabels[type] || type,
    color: colorForType(type),
  }))
})

function normalizedType(node: NodeItem) {
  const labels = node.labels || []
  const type = node.type || labels.find((label) => label !== 'Entity') || labels[0] || 'Entity'
  if (/customer|person/i.test(type)) return 'Customer'
  if (/account/i.test(type)) return 'Account'
  if (/merchant|organization|counterparty/i.test(type)) return 'Merchant'
  if (/device/i.test(type)) return 'Device'
  if (/signal/i.test(type)) return 'RiskSignal'
  if (/event|episode/i.test(type)) return 'RiskEvent'
  return type
}

function colorForType(type: string) {
  return palette[type] || palette.Entity
}

function nodeColor(node: NodeItem) {
  return colorForType(normalizedType(node))
}

function nodeRadius(node: NodeItem) {
  if (normalizedType(node) === 'RiskEvent') return 31
  return 19 + Math.min(11, connectedCount(node.id) * 2.2)
}

function connectedCount(nodeId: string) {
  return props.edges.filter((edge) => edge.source === nodeId || edge.target === nodeId).length
}

function short(text?: string, limit = 24) {
  const value = String(text || '')
  return value.length > limit ? `${value.slice(0, limit)}...` : value
}

function displayName(node: NodeItem) {
  return node.label || node.properties?.name || node.properties?.id_number || node.id
}

function propsEntries(data?: Record<string, any>) {
  return Object.entries(data || {}).filter(([, value]) => value !== null && value !== undefined && value !== '')
}

function formatValue(value: any) {
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'object' && value !== null) return JSON.stringify(value, null, 2)
  return String(value)
}

function detailName() {
  if (!selected.value) return ''
  const data = selected.value.data
  return selected.value.kind === 'node' ? displayName(data) : data.label || data.type
}

function detailElementId() {
  const data = selected.value?.data
  return data?.neo4j_element_id || data?.properties?.elementId || data?.id || ''
}

function graphPoint(event: PointerEvent) {
  const svg = event.currentTarget instanceof SVGElement
    ? event.currentTarget.closest('svg')
    : null
  if (!svg) return { x: 0, y: 0 }
  const rect = svg.getBoundingClientRect()
  const x = ((event.clientX - rect.left) / rect.width) * layout.value.width
  const y = ((event.clientY - rect.top) / rect.height) * layout.value.height
  return {
    x: (x - pan.value.x) / zoom.value,
    y: (y - pan.value.y) / zoom.value,
  }
}

function wheel(event: WheelEvent) {
  event.preventDefault()
  const next = zoom.value + (event.deltaY > 0 ? -0.08 : 0.08)
  zoom.value = Math.max(0.35, Math.min(2.6, next))
}

function pointerDown(event: PointerEvent) {
  dragging.value = true
  dragStart.value = { x: event.clientX, y: event.clientY, px: pan.value.x, py: pan.value.y }
}

function pointerMove(event: PointerEvent) {
  if (nodeDrag.value) {
    const point = graphPoint(event)
    manualPositions.value = {
      ...manualPositions.value,
      [nodeDrag.value.id]: {
        x: Math.max(42, Math.min(layout.value.width - 42, point.x - nodeDrag.value.dx)),
        y: Math.max(42, Math.min(layout.value.height - 42, point.y - nodeDrag.value.dy)),
      },
    }
    return
  }
  if (!dragging.value) return
  pan.value = {
    x: dragStart.value.px + event.clientX - dragStart.value.x,
    y: dragStart.value.py + event.clientY - dragStart.value.y,
  }
}

function pointerUp() {
  dragging.value = false
  nodeDrag.value = null
}

function resetView() {
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
  manualPositions.value = {}
}

function nodePointerDown(event: PointerEvent, node: NodeItem) {
  selectItem('node', node)
  const point = graphPoint(event)
  const position = layout.value.positions[node.id]
  nodeDrag.value = {
    id: node.id,
    dx: point.x - position.x,
    dy: point.y - position.y,
  }
}

function selectItem(kind: 'node' | 'edge', data: any) {
  selected.value = { kind, data }
  detailOpen.value = true
}

function closeDetail() {
  detailOpen.value = false
  selected.value = null
}

function resetGraphState() {
  selected.value = null
  detailOpen.value = true
  zoom.value = 1
  pan.value = { x: 0, y: 0 }
  dragging.value = false
  nodeDrag.value = null
  manualPositions.value = {}
  fullscreen.value = false
}

watch(
  () => [props.nodes, props.edges],
  () => {
    resetGraphState()
  },
  { deep: true },
)
</script>

<template>
  <div :class="graphClass">
    <div class="graph-miro-toolbar">
      <div>
        <strong>Graph Relationship Visualization</strong>
        <span class="muted small">{{ nodes.length }} nodes / {{ layout.edges.length }} edges</span>
      </div>
      <div class="toolbar">
        <button class="button secondary" @click="zoom = Math.min(2.6, zoom + 0.12)">放大</button>
        <button class="button secondary" @click="zoom = Math.max(0.35, zoom - 0.12)">缩小</button>
        <button class="button secondary" @click="resetView">重置</button>
        <button class="button secondary" @click="fullscreen = !fullscreen">
          {{ fullscreen ? '退出全屏' : '全屏' }}
        </button>
      </div>
    </div>

    <div class="graph-miro-body">
      <div class="graph-miro-canvas">
        <svg
          v-if="nodes.length"
          class="graph-miro-svg"
          :viewBox="`0 0 ${layout.width} ${layout.height}`"
          @wheel="wheel"
          @pointerdown="pointerDown"
          @pointermove="pointerMove"
          @pointerup="pointerUp"
          @pointerleave="pointerUp"
        >
          <defs>
            <pattern id="grid" width="26" height="26" patternUnits="userSpaceOnUse">
              <path d="M 26 0 L 0 0 0 26" fill="none" stroke="#d7e0ea" stroke-width="0.7" />
            </pattern>
            <marker
              id="arrow"
              markerWidth="9"
              markerHeight="9"
              refX="10"
              refY="6"
              viewBox="0 0 12 12"
              orient="auto"
              markerUnits="userSpaceOnUse"
            >
              <path d="M2,2 L10,6 L2,10 z" fill="#7f8b99" />
            </marker>
          </defs>
          <rect :width="layout.width" :height="layout.height" fill="url(#grid)" opacity="0.45" />
          <g :transform="viewTransform">
            <g v-for="edge in layout.edges" :key="edge.id || `${edge.source}-${edge.target}-${edge.label}`">
              <path
                :d="edge.path"
                class="miro-edge"
                marker-end="url(#arrow)"
                @click.stop="selectItem('edge', edge)"
              />
              <text
                class="miro-edge-label"
                :x="edge.labelX"
                :y="edge.labelY"
                text-anchor="middle"
                @click.stop="selectItem('edge', edge)"
              >
                {{ short(edge.label || edge.type, 28) }}
              </text>
            </g>

            <g
              v-for="node in nodes"
              :key="node.id"
              class="miro-node"
              @pointerdown.stop="nodePointerDown($event, node)"
              @click.stop="selectItem('node', node)"
            >
              <circle
                :cx="layout.positions[node.id]?.x"
                :cy="layout.positions[node.id]?.y"
                :r="nodeRadius(node)"
                :fill="nodeColor(node)"
              />
              <text
                class="miro-node-name"
                :x="layout.positions[node.id]?.x"
                :y="(layout.positions[node.id]?.y || 0) + nodeRadius(node) + 17"
                text-anchor="middle"
              >
                {{ short(displayName(node), 18) }}
              </text>
            </g>
          </g>
        </svg>
        <div v-else class="panel">
          <p class="muted">暂无图谱数据</p>
        </div>

        <div class="graph-legend">
          <strong>ENTITY TYPES</strong>
          <div class="legend-grid">
            <span v-for="item in legend" :key="item.type" class="legend-item">
              <i :style="{ background: item.color }"></i>{{ item.label }}
            </span>
          </div>
        </div>
      </div>

      <aside v-if="detailOpen" class="miro-detail">
        <template v-if="selected">
          <div class="detail-heading">
            <h3>{{ selected.kind === 'node' ? 'Node Details' : 'Edge Details' }}</h3>
            <button class="button secondary icon-button" title="关闭详情" @click="closeDetail">×</button>
          </div>
          <span v-if="selected.kind === 'node'" class="detail-pill">
            {{ typeLabels[normalizedType(selected.data)] || normalizedType(selected.data) }}
          </span>
          <div class="detail-section">
            <span>Name</span>
            <strong>{{ detailName() }}</strong>
          </div>
          <div class="detail-section">
            <span>Element ID</span>
            <strong>{{ detailElementId() }}</strong>
          </div>
          <div v-if="selected.data.properties?.uuid" class="detail-section">
            <span>UUID</span>
            <strong>{{ selected.data.properties.uuid }}</strong>
          </div>
          <div class="detail-section">
            <span>{{ selected.kind === 'node' ? 'Labels' : 'Type' }}</span>
            <strong>{{ selected.data.type }}</strong>
          </div>
          <button
            v-if="expandable && selected.kind === 'node'"
            class="button"
            @click="emit('expand', selected.data)"
          >
            扩展关联节点
          </button>
          <h4>Properties</h4>
          <div class="props-list">
            <div v-for="[key, value] in propsEntries(selected.data.properties)" :key="key" class="prop-row">
              <span>{{ key }}</span>
              <strong>{{ formatValue(value) }}</strong>
            </div>
          </div>
        </template>
        <div v-else class="detail-empty">
          <div class="detail-heading">
            <h3>详情</h3>
            <button class="button secondary icon-button" title="关闭详情" @click="closeDetail">×</button>
          </div>
          <p class="muted">点击图中的节点或边查看详细信息。</p>
        </div>
      </aside>
    </div>
  </div>
</template>
