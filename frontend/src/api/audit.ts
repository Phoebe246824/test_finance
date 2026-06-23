import { http } from './http'

export async function listAuditLogs(params: Record<string, unknown> = {}) {
  const { data } = await http.get('/api/audit-logs', { params })
  return data
}
