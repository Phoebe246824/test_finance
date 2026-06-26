export function errorMessage(err: unknown, fallback: string): string {
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

type RuntimeScalarType = 'bool' | 'int' | 'float' | 'string' | 'list'

type RuntimeConfigValue = boolean | number | string | string[]

type RuntimeFieldLike = {
  readonly env?: string
  readonly group?: string
  readonly key_path?: string
  readonly label?: string
  readonly help?: string
  readonly scalar_type: RuntimeScalarType
  readonly default?: RuntimeConfigValue
  readonly secret?: boolean
  readonly editable?: boolean
  readonly effective_scope?: string
}

export type RuntimeFieldView = RuntimeFieldLike & {
  readonly env: string
  readonly group: string
  readonly key_path: string
  readonly label: string
  readonly help: string
  readonly default: RuntimeConfigValue
  readonly secret: boolean
  readonly editable: boolean
  readonly effective_scope: string
  readonly value: RuntimeConfigValue
  readonly scopeLabel: string
}

export type RuntimeConfigGroupView = {
  readonly group: string
  readonly title: string
  readonly matches: number
  readonly fields: RuntimeFieldView[]
}

type FeedbackResult = {
  readonly success: boolean
  readonly message: string
}

type Feedback = {
  readonly kind: 'notice' | 'error'
  readonly message: string
}

type DateFormatConfig = {
  readonly timezone: string
  readonly dateFormat: string
  readonly language: string
}

function feedbackFromResult(result: FeedbackResult): Feedback {
  return {
    kind: result.success ? 'notice' : 'error',
    message: result.message,
  }
}

export function modelTestFeedback(result: FeedbackResult): Feedback {
  return feedbackFromResult(result)
}

export function notificationTestFeedback(result: FeedbackResult): Feedback {
  return feedbackFromResult(result)
}

function pad2(value: number): string {
  return String(value).padStart(2, '0')
}

export function formatSystemDate(value: Date, config: DateFormatConfig): string {
  if (config.timezone !== 'Asia/Shanghai (UTC+08:00)' || config.dateFormat !== 'YYYY-MM-DD HH:mm:ss') {
    return value.toLocaleString(config.language === '简体中文' ? 'zh-CN' : undefined)
  }
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(value)
  const partMap = new Map(parts.map((part) => [part.type, part.value]))
  return [
    `${partMap.get('year')}-${partMap.get('month')}-${partMap.get('day')}`,
    `${pad2(Number(partMap.get('hour') || 0))}:${partMap.get('minute')}:${partMap.get('second')}`,
  ].join(' ')
}

export const defaultSystemConfig = {
  name: 'Sentinel Edge 金融风控智能体系统',
  description: '端侧部署的金融风控智能体系统，支持反欺诈、反洗钱、贷前风控等场景。',
  timezone: 'Asia/Shanghai (UTC+08:00)',
  dateFormat: 'YYYY-MM-DD HH:mm:ss',
  language: '简体中文',
} as const

export const defaultModelParams = {
  maxTokens: 2048,
  temperature: 0.2,
  topP: 0.9,
  repetitionPenalty: 1.1,
  timeout: 60,
  concurrency: 2,
} as const

export const defaultNotificationEvents = [
  '高风险事件',
  '黑名单命中',
  '系统异常',
  '模型服务异常',
] as const

function normalizedQueryParts(query: string): string[] {
  return query
    .trim()
    .toLowerCase()
    .split(/\s+/)
    .filter(Boolean)
}

function titleForGroup(group: string): string {
  return group.replace(/[_-]+/g, ' ').replace(/\b\w/g, (char) => char.toUpperCase())
}

export function runtimeScopeLabel(scope: string): string {
  switch (scope) {
    case 'runtime_immediate':
      return '即时生效'
    case 'web_restart':
      return '需重启后端'
    case 'frontend_rebuild':
      return '需重建前端'
    case 'compose_recreate':
      return '需重建依赖服务'
    case 'display_only':
      return '只读展示'
    default:
      return '需额外处理'
  }
}

export function parseListEditorValue(text: string): string[] {
  const values = text
    .split(/[\n,]/)
    .map((item) => item.trim())
    .filter(Boolean)
  return [...new Set(values)]
}

export function serializeListEditorValue(values: string[]): string {
  return values.join('\n')
}

export function normalizeRuntimeFieldValue(
  field: RuntimeFieldLike,
  value: RuntimeConfigValue,
): RuntimeConfigValue {
  switch (field.scalar_type) {
    case 'bool':
      return value === true
    case 'int':
      return typeof value === 'number' ? Math.trunc(value) : 0
    case 'float':
      return typeof value === 'number' ? value : 0
    case 'list':
      return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
    case 'string':
    default:
      return typeof value === 'string' ? value : ''
  }
}

function matchesField(field: RuntimeFieldView, queryParts: string[]): boolean {
  if (!queryParts.length) return true
  const haystack = [
    field.group,
    field.label,
    field.env,
    field.help,
  ]
    .join(' ')
    .toLowerCase()
  return queryParts.some((part) => haystack.includes(part))
}

export function buildConfigGroups(
  runtimeConfig: Record<string, RuntimeConfigValue>,
  metadata: RuntimeFieldLike[],
  query = '',
): RuntimeConfigGroupView[] {
  const queryParts = normalizedQueryParts(query)
  const groups = new Map<string, RuntimeFieldView[]>()

  for (const field of metadata) {
    if (typeof field.env !== 'string' || !field.env) continue
    const normalizedField: RuntimeFieldView = {
      env: field.env,
      group: field.group || 'other',
      key_path: field.key_path || `runtime_config.${field.env}`,
      label: field.label || field.env,
      help: field.help || '',
      scalar_type: field.scalar_type,
      default: normalizeRuntimeFieldValue(field, (field.default ?? '') as RuntimeConfigValue),
      secret: field.secret === true,
      editable: field.editable !== false,
      effective_scope: field.effective_scope || 'web_restart',
      value: normalizeRuntimeFieldValue(field, runtimeConfig[field.env] as RuntimeConfigValue),
      scopeLabel: runtimeScopeLabel(field.effective_scope || 'web_restart'),
    }

    if (!matchesField(normalizedField, queryParts)) continue

    const current = groups.get(normalizedField.group) || []
    current.push(normalizedField)
    groups.set(normalizedField.group, current)
  }

  return [...groups.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([group, fields]) => ({
      group,
      title: titleForGroup(group),
      matches: fields.length,
      fields: fields.sort((left, right) => left.label.localeCompare(right.label, 'zh-CN')),
    }))
}
