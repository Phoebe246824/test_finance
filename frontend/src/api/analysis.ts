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

export async function getAnalysisTask(taskId: string): Promise<AnalysisTask> {
  const { data } = await http.get(`/api/tasks/${taskId}`)
  return data
}

export async function analyzeText(
  text: string,
  onTaskUpdate?: (task: AnalysisTask) => void,
): Promise<AnalyzeResult> {
  const task = await createAnalysisTask(text)
  onTaskUpdate?.(task)
  const started = Date.now()
  while (Date.now() - started < 300000) {
    await new Promise((resolve) => window.setTimeout(resolve, 1200))
    const current = await getAnalysisTask(task.task_id)
    onTaskUpdate?.(current)
    if (current.status === 'failed') {
      throw new Error(current.error_message || '分析任务失败')
    }
    if (current.status === 'success' && current.event_id) {
      const { data } = await http.get(`/api/events/${current.event_id}`)
      return {
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
      } as AnalyzeResult
    }
  }
  throw new Error('分析任务超时')
}

export async function listDemoCases() {
  const { data } = await http.get('/api/demo-cases')
  return data
}
