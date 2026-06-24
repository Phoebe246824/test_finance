import { http } from './http'

export type BlacklistType = 'persons' | 'keywords' | 'events'

export async function listBlacklist(type: BlacklistType) {
  const { data } = await http.get(`/api/blacklist/${type}`)
  return data
}

export async function createBlacklistItem(
  type: BlacklistType,
  payload: { value: string; summary?: string; description?: string },
) {
  const { data } = await http.post(`/api/blacklist/${type}`, payload)
  return data
}

export async function updateBlacklistItem(
  type: BlacklistType,
  value: string,
  payload: { value: string; summary?: string; description?: string },
) {
  const { data } = await http.put(`/api/blacklist/${type}/${encodeURIComponent(value)}`, payload)
  return data
}

export async function deleteBlacklistItem(type: BlacklistType, value: string) {
  const { data } = await http.delete(`/api/blacklist/${type}/${encodeURIComponent(value)}`)
  return data
}
