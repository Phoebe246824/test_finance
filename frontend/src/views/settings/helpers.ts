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
