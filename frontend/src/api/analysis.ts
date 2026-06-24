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
  status: 'queued' | 'running' | 'success' | 'failed'
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

export async function createAnalysisTask(text: string): Promise<AnalysisTask> {
  const { data } = await http.post('/api/tasks/analyze', { text })
  return data
}

const SSE_TIMEOUT_MS = 5 * 60 * 1000

export interface AnalysisController {
  abort: () => void
}

export async function analyzeText(
  text: string,
  onTaskUpdate?: (task: AnalysisTask) => void,
  signal?: AbortSignal,
): Promise<AnalyzeResult> {
  const task = await createAnalysisTask(text)
  onTaskUpdate?.(task)

  if (signal?.aborted) {
    throw new DOMException('Aborted', 'AbortError')
  }

  return new Promise((resolve, reject) => {
    let token = ''
    try {
      const saved = localStorage.getItem('sentinel:auth')
      token = saved ? JSON.parse(saved).token : ''
    } catch {
      // ignore corrupted localStorage
    }
    const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
    const params = token ? `?token=${encodeURIComponent(token)}` : ''
    const es = new EventSource(`${baseUrl}/api/tasks/${task.task_id}/stream${params}`)
    let closed = false

    const cleanup = () => {
      if (!closed) {
        closed = true
        clearTimeout(timeoutId)
        es.close()
      }
    }

    const timeoutId = window.setTimeout(() => {
      cleanup()
      reject(new Error('分析超时，请重试'))
    }, SSE_TIMEOUT_MS)

    if (signal) {
      signal.addEventListener('abort', () => {
        cleanup()
        reject(new DOMException('Aborted', 'AbortError'))
      }, { once: true })
    }

    es.addEventListener('update', (e) => {
      if (closed) return
      let current: AnalysisTask
      try {
        current = JSON.parse(e.data)
      } catch {
        cleanup()
        reject(new Error('SSE 数据解析失败'))
        return
      }
      onTaskUpdate?.(current)

      if (current.status === 'failed') {
        cleanup()
        reject(new Error(current.error_message || '分析任务失败'))
        return
      }
      if (current.status === 'success' && current.event_id) {
        cleanup()
        http.get(`/api/events/${current.event_id}`).then(({ data }) => {
          resolve({
            event_id: data.event_id,
            status: data.status,
            risk_level: data.risk_level,
            risk_score: data.risk_score,
            event_type: data.event_type,
            summary: data.summary,
            reasoning: data.reasoning,
            blacklist: {
              decision: data.blacklist_decision,
              matched_persons: data.matched_persons || [],
              matched_keywords: data.matched_keywords || [],
              event_similarity: data.event_similarity || {},
            },
            graph_result: null,
            second_risk_applied: false,
            dimension_scores: data.dimension_scores || {},
            trend_report: data.trend_report || {},
          } as AnalyzeResult)
        }).catch(reject)
      }
    })

    es.onerror = () => {
      if (closed) return
      cleanup()
      reject(new Error('SSE 连接失败'))
    }
  })
}

export async function listDemoCases() {
  const { data } = await http.get('/api/demo-cases')
  return data
}
