import { http } from './http'

export async function listEvents(params: Record<string, unknown> = {}) {
  const { data } = await http.get('/api/events', { params })
  return data
}

export async function getEvent(eventId: string) {
  const { data } = await http.get(`/api/events/${eventId}`)
  return data
}

export async function getEventGraph(eventId: string) {
  const { data } = await http.get(`/api/graph/events/${eventId}`)
  return data
}

export async function searchPersonGraph(keyword: string) {
  const { data } = await http.get('/api/graph/persons', { params: { q: keyword } })
  return data
}

export async function expandGraphNode(nodeId: string) {
  const { data } = await http.get(`/api/graph/nodes/${encodeURIComponent(nodeId)}/expand`)
  return data
}

export async function deleteEvent(eventId: string) {
  const { data } = await http.delete(`/api/events/${eventId}`)
  return data
}

export async function createReviewAction(
  eventId: string,
  payload: { action_type: string; comment?: string },
) {
  const { data } = await http.post(`/api/events/${eventId}/review-actions`, payload)
  return data
}
