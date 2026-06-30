import { http } from './http'

export type HealthStatus = {
  readonly ok: boolean
  readonly detail: string
}

export type HealthResponse = {
  readonly api: HealthStatus
  readonly milvus: HealthStatus
  readonly neo4j: HealthStatus
  readonly llm: HealthStatus
}

export type HardwareResponse = Record<string, boolean | number | readonly string[] | string | null | undefined>

export type RuntimeResponse = {
  readonly process_id: number
  readonly uptime_seconds: number
  readonly python: string
  readonly storage_backend: string
  readonly event_count: number
  readonly review_count: number
  readonly blacklist_count: number
  readonly latest_event_at: string
  readonly recent_analysis?: readonly any[]
  readonly analysis_latency_series: readonly {
    readonly label: string
    readonly seconds: number
  }[]
}

export async function getHealth() {
  const { data } = await http.get('/api/system/health')
  return data as HealthResponse
}

export async function getHardware() {
  const { data } = await http.get('/api/system/hardware')
  return data as HardwareResponse
}

export async function getRuntime() {
  const { data } = await http.get('/api/system/runtime')
  return data as RuntimeResponse
}
