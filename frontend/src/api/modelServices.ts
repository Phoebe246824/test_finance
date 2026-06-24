import { http } from './http'

export type ModelService = {
  readonly name: string
  readonly type: string
  readonly deployment: string
  readonly endpoint: string
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
