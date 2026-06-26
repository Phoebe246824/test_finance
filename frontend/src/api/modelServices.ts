import { http } from './http'

export type ModelService = {
  readonly name: string
  readonly type: string
  readonly deployment: string
  readonly endpoint: string
  readonly apiKey: string
  readonly status: string
  readonly default: boolean
  readonly updatedAt: string
}

export type ModelServiceListResponse = {
  readonly services: readonly ModelService[]
  readonly total: number
}

export async function listModelServices(): Promise<ModelServiceListResponse> {
  const { data } = await http.get('/api/model-services')
  return data as ModelServiceListResponse
}

export async function createModelService(payload: {
  name: string
  type: string
  deployment?: string
  endpoint: string
  apiKey?: string
  status?: string
  default?: boolean
}): Promise<{ service: ModelService }> {
  const { data } = await http.post('/api/model-services', payload)
  return data as { service: ModelService }
}

export async function updateModelService(
  serviceName: string,
  payload: {
    name: string
    type: string
    deployment?: string
    endpoint: string
    apiKey?: string
    default?: boolean
  },
): Promise<{ service: ModelService }> {
  const { data } = await http.put(
    `/api/model-services/${encodeURIComponent(serviceName)}`,
    payload,
  )
  return data as { service: ModelService }
}

export async function deleteModelService(
  serviceName: string,
): Promise<{ deleted: boolean; name: string }> {
  const { data } = await http.delete(
    `/api/model-services/${encodeURIComponent(serviceName)}`,
  )
  return data as { deleted: boolean; name: string }
}

export async function testModelService(
  endpoint: string,
  type: string,
  apiKey = '',
): Promise<{ success: boolean; message: string; endpoint: string }> {
  const { data } = await http.post('/api/model-services/test', { endpoint, type, apiKey })
  return data as { success: boolean; message: string; endpoint: string }
}

export async function testSavedModelService(
  serviceName: string,
): Promise<{
  result: { success: boolean; message: string; endpoint: string }
  service: ModelService
}> {
  const { data } = await http.post(
    `/api/model-services/${encodeURIComponent(serviceName)}/test`,
  )
  return data as {
    result: { success: boolean; message: string; endpoint: string }
    service: ModelService
  }
}
