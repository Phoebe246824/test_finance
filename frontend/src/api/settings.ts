import { http } from './http'

export type SystemConfig = {
  name: string
  description: string
  timezone: string
  dateFormat: string
  language: string
}

export type ModelParams = {
  maxTokens: number
  temperature: number
  topP: number
  repetitionPenalty: number
  timeout: number
  concurrency: number
}

export type ModelService = {
  name: string
  type: string
  deployment: string
  endpoint: string
  apiKey: string
  status: string
  default: boolean
  updatedAt: string
}

export type ManagedUser = {
  username: string
  name: string
  role: string
  status: string
  lastLogin: string
}

export type DataManagement = {
  summary: Array<{ label: string; value: string }>
  retentionDays: number
}

export type NotificationChannel = {
  name: string
  enabled: boolean
  target: string
}

export type RuntimeScalarType = 'bool' | 'int' | 'float' | 'string' | 'list'

export type RuntimeEffectiveScope =
  | 'runtime_immediate'
  | 'web_restart'
  | 'frontend_rebuild'
  | 'compose_recreate'
  | 'display_only'
  | string

export type RuntimeConfigValue = boolean | number | string | string[]

export type RuntimeConfigField = {
  env: string
  group: string
  key_path: string
  label: string
  help: string
  scalar_type: RuntimeScalarType
  default: RuntimeConfigValue
  secret: boolean
  editable: boolean
  effective_scope: RuntimeEffectiveScope
}

export type AppSettings = {
  system_config: SystemConfig
  model_params: ModelParams
  model_services: ModelService[]
  users: ManagedUser[]
  data_management: DataManagement
  notification_channels: NotificationChannel[]
  notification_events: string[]
  runtime_config: Record<string, RuntimeConfigValue>
  runtime_config_metadata: RuntimeConfigField[]
}

export type AppSettingsResponse = {
  settings: AppSettings
  updated_at: string
}

export async function getAppSettings() {
  const { data } = await http.get('/api/settings')
  return data as AppSettingsResponse
}

export async function updateAppSettings(settings: AppSettings) {
  const { data } = await http.put('/api/settings', settings)
  return data as AppSettingsResponse
}

export async function updateSystemConfig(systemConfig: SystemConfig) {
  const { data } = await http.put('/api/settings/system-config', systemConfig)
  return data as AppSettingsResponse
}

export async function updateModelParams(modelParams: ModelParams) {
  const { data } = await http.put('/api/settings/model-params', modelParams)
  return data as AppSettingsResponse
}

export async function updateDataManagement(dataManagement: DataManagement) {
  const { data } = await http.put('/api/settings/data-management', dataManagement)
  return data as AppSettingsResponse
}

export async function updateNotificationEvents(notificationEvents: string[]) {
  const { data } = await http.put('/api/settings/notification-events', notificationEvents)
  return data as AppSettingsResponse
}

export async function runDataManagementCleanup() {
  const { data } = await http.post('/api/settings/data-management/cleanup')
  return data as { enabled: boolean; deleted: number; status: string }
}
