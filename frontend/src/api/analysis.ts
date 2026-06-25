import { http } from './http'

export interface AnalyzeResult {
  event_id: string
  status: string
  risk_level?: string
  risk_score?: number
  event_type?: string
  summary?: string
  reasoning?: string
  blacklist: Record<string, unknown>
  graph_result?: Record<string, unknown> | null
  second_risk_applied: boolean
  dimension_scores?: Record<string, number>
  trend_report?: Record<string, unknown>
}

export interface PipelineProgress {
  stage_key: string
  stage_label: string
  stage_index: number
  stage_total: number
  stage_detail: string
  stage_updated_at?: string
}

export interface AnalysisTask {
  task_id: string
  event_id?: string
  status: 'queued' | 'running' | 'success' | 'failed' | 'cancelled'
  error_message?: string
  started_at?: string
  finished_at?: string
  stage_key?: string
  stage_label?: string
  stage_index?: number
  stage_total?: number
  stage_detail?: string
  stage_updated_at?: string
}

export async function analyzeTextSync(text: string): Promise<AnalyzeResult> {
  const { data } = await http.post('/api/analyze', { text })
  return data
}

export async function createAnalysisTask(
  text: string,
  signal?: AbortSignal,
): Promise<AnalysisTask> {
  const { data } = await http.post('/api/tasks/analyze', { text }, { signal })
  return data
}

export async function cancelAnalysisTask(taskId: string): Promise<AnalysisTask> {
  const { data } = await http.delete(`/api/tasks/${taskId}`)
  return data
}

const SSE_TIMEOUT_MS = 5 * 60 * 1000

export async function analyzeText(
  text: string,
  onTaskUpdate?: (task: AnalysisTask) => void,
  signal?: AbortSignal,
): Promise<AnalyzeResult> {
  if (signal?.aborted) {
    throw new DOMException('Aborted', 'AbortError')
  }

  const task = await createAnalysisTask(text, signal)
  onTaskUpdate?.(task)

  if (signal?.aborted) {
    await cancelAnalysisTask(task.task_id)
    throw new DOMException('Aborted', 'AbortError')
  }

  return new Promise((resolve, reject) => {
    let token = ''
    try {
      const saved = localStorage.getItem('sentinel:auth')
      token = saved ? JSON.parse(saved).token : ''
    } catch {
      token = ''
    }

    http.get(`/api/tasks/${task.task_id}`, { signal }).then(() => {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
      const params = token ? `?token=${encodeURIComponent(token)}` : ''
      const es = new EventSource(`${baseUrl}/api/tasks/${task.task_id}/stream${params}`)
      let closed = false
      let abortHandler: (() => void) | null = null

      const cleanup = () => {
        if (!closed) {
          closed = true
          clearTimeout(timeoutId)
          es.close()
          if (abortHandler && signal) {
            signal.removeEventListener('abort', abortHandler)
          }
        }
      }

      const timeoutId = window.setTimeout(() => {
        cleanup()
        reject(new Error('分析超时，请重试'))
      }, SSE_TIMEOUT_MS)

      if (signal) {
        abortHandler = () => {
          cleanup()
          cancelAnalysisTask(task.task_id).finally(() => {
            reject(new DOMException('Aborted', 'AbortError'))
          })
        }
        signal.addEventListener('abort', abortHandler, { once: true })
      }

      es.addEventListener('update', (e) => {
        if (closed) return
        let current: AnalysisTask
        try {
          current = JSON.parse(e.data)
        } catch {
          cleanup()
          reject(new Error('进度流异常，请重试'))
          return
        }
        onTaskUpdate?.(current)

        if (current.status === 'cancelled') {
          cleanup()
          reject(new DOMException('Aborted', 'AbortError'))
          return
        }
        if (current.status === 'failed') {
          cleanup()
          reject(new Error(current.error_message || '分析任务失败'))
          return
        }
        if (current.status === 'success') {
          cleanup()
          if (!current.event_id) {
            resolve(emptySuccessResult())
            return
          }
          http.get(`/api/events/${current.event_id}`, { signal }).then(({ data }) => {
            resolve(eventToAnalyzeResult(data))
          }).catch((err) => {
            if (err?.name === 'CanceledError' || err?.name === 'AbortError') {
              reject(new DOMException('Aborted', 'AbortError'))
              return
            }
            reject(new Error('分析完成但事件详情未找到，请刷新事件库'))
          })
        }
      })

      es.onerror = () => {
        if (closed) return
        if (es.readyState === EventSource.CLOSED) {
          cleanup()
          reject(new Error('SSE 连接失败'))
        }
      }
    }).catch((err) => {
      if (err?.name === 'CanceledError' || err?.name === 'AbortError') {
        reject(new DOMException('Aborted', 'AbortError'))
        return
      }
      reject(new Error('任务不存在或无权访问'))
    })
  })
}

function emptySuccessResult(): AnalyzeResult {
  return {
    event_id: '',
    status: 'success',
    blacklist: {
      decision: null,
      matched_persons: [],
      matched_keywords: [],
      event_similarity: {},
    },
    graph_result: null,
    second_risk_applied: false,
  }
}

function eventToAnalyzeResult(data: Record<string, unknown>): AnalyzeResult {
  return {
    event_id: String(data.event_id || ''),
    status: String(data.status || ''),
    risk_level: data.risk_level as string | undefined,
    risk_score: data.risk_score as number | undefined,
    event_type: data.event_type as string | undefined,
    summary: data.summary as string | undefined,
    reasoning: data.reasoning as string | undefined,
    blacklist: {
      decision: data.blacklist_decision,
      matched_persons: data.matched_persons || [],
      matched_keywords: data.matched_keywords || [],
      event_similarity: data.event_similarity || {},
    },
    graph_result: null,
    second_risk_applied: Boolean(data.second_risk_applied ?? false),
    dimension_scores: (data.dimension_scores || {}) as Record<string, number>,
    trend_report: (data.trend_report || {}) as Record<string, unknown>,
  }
}

export async function listDemoCases() {
  const { data } = await http.get('/api/demo-cases')
  return data
}
