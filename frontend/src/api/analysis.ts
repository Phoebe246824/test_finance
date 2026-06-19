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
  graph_result?: Record<string, unknown>
  second_risk_applied: boolean
}

export async function analyzeText(text: string): Promise<AnalyzeResult> {
  const { data } = await http.post('/api/analyze', { text })
  return data
}
