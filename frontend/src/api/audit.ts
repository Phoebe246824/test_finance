import { http } from './http'

export type AuditLog = {
  readonly id: number
  readonly actor: string
  readonly role: string
  readonly action: string
  readonly resource_type: string
  readonly resource_id: string | null
  readonly detail: Record<string, unknown>
  readonly detail_json?: string
  readonly created_at: string
}

export type AuditLogResponse = {
  readonly total: number
  readonly page: number
  readonly page_size: number
  readonly items: readonly AuditLog[]
}

export async function listAuditLogs(
  params: Record<string, unknown> = {},
): Promise<AuditLogResponse> {
  const { data } = await http.get('/api/audit-logs', { params })
  return data as AuditLogResponse
}
