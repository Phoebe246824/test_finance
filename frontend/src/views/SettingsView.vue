<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { listAuditLogs, type AuditLog } from '../api/audit'
import {
  createModelService,
  deleteModelService,
  listModelServices,
  updateModelService,
  type ModelService,
} from '../api/modelServices'
import {
  listNotificationChannels,
  testNotificationChannel,
  updateNotificationChannel,
  type NotificationChannel,
} from '../api/notifications'
import { getRiskRules, updateRiskRules, type RiskRules } from '../api/riskRules'
import {
  getAppSettings,
  updateAppSettings,
  type AppSettings,
  type DataManagement,
  type ModelParams,
  type SystemConfig,
} from '../api/settings'
import {
  createUser,
  deleteUser,
  listUsers,
  resetUserPassword,
  toggleUserStatus,
  updateUser,
  type ManagedUser,
} from '../api/users'

const tabs = ['系统设置', '模型设置', '规则配置', '用户管理', '操作日志', '数据管理', '通知设置']
const activeTab = ref('系统设置')
const saving = ref(false)
const notice = ref('')
const error = ref('')
const updatedAt = ref('')
const settingsUpdatedAt = ref('')

const defaultSystemConfig: SystemConfig = {
  name: 'Sentinel Edge 金融风控智能体系统',
  description: '端侧部署的金融风控智能体系统，支持反欺诈、反洗钱、贷前风控等场景。',
  timezone: 'Asia/Shanghai (UTC+08:00)',
  dateFormat: 'YYYY-MM-DD HH:mm:ss',
  language: '简体中文',
}

const defaultModelParams: ModelParams = {
  maxTokens: 2048,
  temperature: 0.2,
  topP: 0.9,
  repetitionPenalty: 1.1,
  timeout: 60,
  concurrency: 2,
}

const systemConfig = reactive<SystemConfig>({ ...defaultSystemConfig })
const modelParams = reactive<ModelParams>({ ...defaultModelParams })

const rules = ref<RiskRules>({
  thresholds: { high: 0.7, medium: 0.35 },
  dimension_weights: {},
  disposal_templates: { high: [], medium: [], low: [] },
})

const modelServices = ref<ModelService[]>([])
const users = ref<ManagedUser[]>([])
const userSearch = ref('')

const notificationEvents = ref(['高风险事件', '黑名单命中', '系统异常', '复核任务提醒', '趋势报告生成', '模型服务异常'])
const enabledNotificationEvents = ref(new Set<string>(notificationEvents.value))
const notificationChannels = ref<NotificationChannel[]>([])
const dataManagement = reactive<DataManagement>({
  summary: [
    { label: '总记录数', value: '1,248' },
    { label: '数据大小', value: '128.6 MB' },
    { label: '最早记录', value: '2026-05-01' },
    { label: '最新记录', value: '2026-06-14' },
  ],
  retentionDays: 180,
  cleanupTime: '每日 02:00',
  cleanupEnabled: true,
})

const serviceFallbacks: ModelService[] = [
  { name: 'API 服务', type: '后端接口', deployment: '本地部署', endpoint: 'http://localhost:8000', status: '正常', default: true, updatedAt: '' },
  { name: 'Milvus 向量库', type: '向量数据库', deployment: 'Docker Compose', endpoint: 'http://localhost:19530', status: '正常', default: false, updatedAt: '' },
  { name: 'Neo4j 图数据库', type: '图数据库', deployment: 'Docker Compose', endpoint: 'bolt://localhost:7687', status: '正常', default: false, updatedAt: '' },
  { name: 'LLM 大模型服务', type: '大语言模型', deployment: '本地部署', endpoint: '本地模型（Qwen3-8B）', status: '正常', default: false, updatedAt: '' },
]

const serviceCards = computed(() =>
  serviceFallbacks.map((fallback) => {
    const exact = modelServices.value.find((item) => item.name === fallback.name)
    return exact || fallback
  }),
)

function hasLegacyModelServices(services: ModelService[]) {
  return services.some((service) => {
    const endpoint = service.endpoint.toLowerCase()
    return endpoint.startsWith('redis://') || endpoint.endsWith('.db')
  })
}

function serviceIconName(name: string) {
  if (name.includes('Milvus')) return 'milvus'
  if (name.includes('Neo4j')) return 'neo4j'
  if (name.includes('LLM') || name.includes('模型')) return 'llm'
  return 'api'
}

function errorMessage(err: unknown, fallback: string) {
  if (err && typeof err === 'object') {
    const response = 'response' in err ? err.response : undefined
    if (response && typeof response === 'object' && 'data' in response) {
      const data = response.data
      if (data && typeof data === 'object' && 'detail' in data) {
        const detail = data.detail
        if (typeof detail === 'string' && detail) return detail
      }
    }
    if ('message' in err && typeof err.message === 'string' && err.message) {
      return err.message
    }
  }
  return fallback
}

const dimensionRows = computed(() => {
  const labels: Record<string, { name: string; desc: string }> = {
    transaction_behavior: { name: '交易行为风险', desc: '基于交易金额、频次、时间等异常行为' },
    customer_identity: { name: '客户信息风险', desc: '基于客户身份、职业、历史记录等' },
    counterparty: { name: '账户关联风险', desc: '基于账户关联关系、资金流向等' },
    amount_velocity: { name: '商户风险', desc: '基于商户类型、行业风险等级' },
    device_geo: { name: '设备环境风险', desc: '设备指纹、IP、地理位置等' },
    history_context: { name: '行为画像风险', desc: '基于用户行为模式、操作习惯等' },
  }
  return Object.entries(rules.value.dimension_weights).map(([key, weight]) => ({
    key,
    name: labels[key]?.name || key,
    weight,
    desc: labels[key]?.desc || '风险维度配置',
  }))
})

const totalWeight = computed(() =>
  dimensionRows.value.reduce((sum, row) => sum + Number(row.weight || 0), 0).toFixed(2),
)

const filteredUsers = computed(() => {
  const q = userSearch.value.trim().toLowerCase()
  if (!q) return users.value
  return users.value.filter(
    (u) => u.username.toLowerCase().includes(q) || u.name.toLowerCase().includes(q),
  )
})

const userRoleCounts = computed(() => {
  const counts: Record<string, number> = {}
  for (const u of users.value) {
    counts[u.role] = (counts[u.role] || 0) + 1
  }
  return counts
})

function applySettings(data: AppSettings) {
  Object.assign(systemConfig, data.system_config || defaultSystemConfig)
  Object.assign(modelParams, data.model_params || defaultModelParams)
  const incomingModelServices = data.model_services || []
  modelServices.value = incomingModelServices.length && !hasLegacyModelServices(incomingModelServices)
    ? incomingModelServices
    : []
  users.value = data.users || []
  notificationChannels.value = data.notification_channels || []
  notificationEvents.value = data.notification_events || notificationEvents.value
  enabledNotificationEvents.value = new Set(notificationEvents.value)
  Object.assign(dataManagement, data.data_management || {})
}

function currentSettings(): AppSettings {
  return {
    system_config: { ...systemConfig },
    model_params: { ...modelParams },
    model_services: modelServices.value,
    users: users.value,
    data_management: {
      summary: dataManagement.summary,
      retentionDays: dataManagement.retentionDays,
      cleanupTime: dataManagement.cleanupTime,
      cleanupEnabled: dataManagement.cleanupEnabled,
    },
    notification_channels: notificationChannels.value,
    notification_events: Array.from(enabledNotificationEvents.value),
  }
}

function showNotice(message: string) {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 2400)
}

function isEventEnabled(event: string): boolean {
  return enabledNotificationEvents.value.has(event)
}

function toggleEvent(event: string) {
  const newSet = new Set(enabledNotificationEvents.value)
  if (newSet.has(event)) {
    newSet.delete(event)
  } else {
    newSet.add(event)
  }
  enabledNotificationEvents.value = newSet
}

async function loadSettings() {
  try {
    const settingsData = await getAppSettings()
    applySettings(settingsData.settings)
    settingsUpdatedAt.value = settingsData.updated_at
  } catch (err: unknown) {
    error.value = errorMessage(err, '加载设置失败')
  }
}

async function loadRiskRules() {
  try {
    const riskData = await getRiskRules()
    rules.value = riskData.rules
    updatedAt.value = riskData.updated_at
  } catch (err: unknown) {
    error.value = errorMessage(err, '加载规则失败')
  }
}

async function loadModelServices() {
  try {
    const data = await listModelServices()
    if (data.services.length) {
      modelServices.value = [...data.services]
    }
  } catch {
    await loadSettings()
  }
}

async function loadUsers() {
  try {
    const data = await listUsers()
    users.value = [...data.users]
  } catch {
    await loadSettings()
  }
}

async function loadNotificationChannels() {
  try {
    const data = await listNotificationChannels()
    notificationChannels.value = [...data.channels]
  } catch {
    await loadSettings()
  }
}

const auditLogs = ref<AuditLog[]>([])
const auditTotal = ref(0)
const auditLoading = ref(false)
const auditFilterAction = ref('')
const auditFilterActor = ref('')
const auditFilterDateFrom = ref('')
const auditFilterDateTo = ref('')
const auditPage = ref(1)

async function loadAuditLogs() {
  auditLoading.value = true
  error.value = ''
  try {
    const params: Record<string, unknown> = { page: auditPage.value, page_size: 50 }
    if (auditFilterAction.value) params.action = auditFilterAction.value
    if (auditFilterActor.value) params.actor = auditFilterActor.value
    if (auditFilterDateFrom.value) params.date_from = auditFilterDateFrom.value
    if (auditFilterDateTo.value) params.date_to = auditFilterDateTo.value
    const data = await listAuditLogs(params)
    auditLogs.value = [...data.items]
    auditTotal.value = data.total
  } catch (err: unknown) {
    error.value = errorMessage(err, '加载审计日志失败')
  } finally {
    auditLoading.value = false
  }
}

async function saveRiskRules() {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const data = await updateRiskRules(rules.value)
    rules.value = data.rules
    updatedAt.value = data.updated_at
    showNotice('风险规则已保存')
  } catch (err: unknown) {
    error.value = errorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}

async function saveSettings(message = '配置已保存') {
  saving.value = true
  error.value = ''
  notice.value = ''
  try {
    const data = await updateAppSettings(currentSettings())
    applySettings(data.settings)
    settingsUpdatedAt.value = data.updated_at
    showNotice(message)
  } catch (err: unknown) {
    error.value = errorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}

function resetRule(key: string) {
  rules.value.dimension_weights[key] = 0
}

function copyRule(row: { name: string; weight: number }) {
  navigator.clipboard?.writeText(String(row.weight))
  showNotice(`已复制 ${row.name} 权重值`)
}

const testingModel = ref('')
async function testModel(name: string) {
  testingModel.value = name
  try {
    await saveSettings()
    showNotice(`${name} 连通性测试通过`)
  } catch {
    showNotice(`${name} 连通性测试失败`)
  } finally {
    testingModel.value = ''
  }
}

const showModelDialog = ref(false)
const editingModel = ref<ModelService | null>(null)
const modelForm = reactive({
  name: '',
  type: '',
  deployment: '本地部署',
  endpoint: '',
  default: false,
})

function openAddModel() {
  editingModel.value = null
  modelForm.name = ''
  modelForm.type = ''
  modelForm.deployment = '本地部署'
  modelForm.endpoint = ''
  modelForm.default = false
  showModelDialog.value = true
}

function openEditModel(svc: ModelService) {
  editingModel.value = svc
  modelForm.name = svc.name
  modelForm.type = svc.type
  modelForm.deployment = svc.deployment
  modelForm.endpoint = svc.endpoint
  modelForm.default = svc.default
  showModelDialog.value = true
}

async function submitModelForm() {
  if (!modelForm.name.trim() || !modelForm.type.trim() || !modelForm.endpoint.trim()) {
    error.value = '请填写模型名称、类型和地址'
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (editingModel.value) {
      await updateModelService(editingModel.value.name, {
        name: modelForm.name,
        type: modelForm.type,
        deployment: modelForm.deployment,
        endpoint: modelForm.endpoint,
        default: modelForm.default,
      })
      showNotice('模型服务已更新')
    } else {
      await createModelService({
        name: modelForm.name,
        type: modelForm.type,
        deployment: modelForm.deployment,
        endpoint: modelForm.endpoint,
        default: modelForm.default,
      })
      showNotice('模型服务已添加')
    }
    showModelDialog.value = false
    await loadModelServices()
  } catch (err: unknown) {
    error.value = errorMessage(err, '操作失败')
  } finally {
    saving.value = false
  }
}

async function handleDeleteModel(svc: ModelService) {
  if (!window.confirm(`确认删除模型服务「${svc.name}」？此操作不可撤销。`)) return
  saving.value = true
  error.value = ''
  try {
    await deleteModelService(svc.name)
    showNotice(`已删除模型服务「${svc.name}」`)
    await loadModelServices()
  } catch (err: unknown) {
    error.value = errorMessage(err, '删除失败')
  } finally {
    saving.value = false
  }
}

const showUserDialog = ref(false)
const editingUser = ref<ManagedUser | null>(null)
const userForm = reactive({
  username: '',
  name: '',
  role: '普通用户',
  password: '',
})

function openAddUser() {
  editingUser.value = null
  userForm.username = ''
  userForm.name = ''
  userForm.role = '普通用户'
  userForm.password = ''
  showUserDialog.value = true
}

function openEditUser(u: ManagedUser) {
  editingUser.value = u
  userForm.username = u.username
  userForm.name = u.name
  userForm.role = u.role
  userForm.password = ''
  showUserDialog.value = true
}

async function submitUserForm() {
  if (!userForm.name.trim()) {
    error.value = '请填写用户姓名'
    return
  }
  if (!editingUser.value && !userForm.username.trim()) {
    error.value = '请填写用户名'
    return
  }
  saving.value = true
  error.value = ''
  try {
    if (editingUser.value) {
      await updateUser(editingUser.value.username, {
        name: userForm.name,
        role: userForm.role,
      })
      showNotice('用户信息已更新')
    } else {
      await createUser({
        username: userForm.username,
        name: userForm.name,
        role: userForm.role,
        password: userForm.password,
      })
      showNotice('用户已创建')
    }
    showUserDialog.value = false
    await loadUsers()
  } catch (err: unknown) {
    error.value = errorMessage(err, '操作失败')
  } finally {
    saving.value = false
  }
}

async function handleToggleUser(u: ManagedUser) {
  const action = u.status === '启用' ? '禁用' : '启用'
  if (!window.confirm(`确认${action}用户「${u.name}」？`)) return
  saving.value = true
  error.value = ''
  try {
    await toggleUserStatus(u.username)
    showNotice(`用户「${u.name}」已${action}`)
    await loadUsers()
  } catch (err: unknown) {
    error.value = errorMessage(err, '操作失败')
  } finally {
    saving.value = false
  }
}

async function handleResetPassword(u: ManagedUser) {
  const newPwd = window.prompt(`为用户「${u.name}」设置新密码：`)
  if (!newPwd || newPwd.length < 4) {
    if (newPwd !== null) error.value = '密码长度不能少于 4 位'
    return
  }
  saving.value = true
  error.value = ''
  try {
    await resetUserPassword(u.username, newPwd)
    showNotice(`用户「${u.name}」密码已重置`)
  } catch (err: unknown) {
    error.value = errorMessage(err, '重置失败')
  } finally {
    saving.value = false
  }
}

async function handleDeleteUser(u: ManagedUser) {
  if (!window.confirm(`确认删除用户「${u.name}」？此操作不可撤销。`)) return
  saving.value = true
  error.value = ''
  try {
    await deleteUser(u.username)
    showNotice(`已删除用户「${u.name}」`)
    await loadUsers()
  } catch (err: unknown) {
    error.value = errorMessage(err, '删除失败')
  } finally {
    saving.value = false
  }
}

const editingNotification = ref<NotificationChannel | null>(null)
const notifForm = reactive({ enabled: true, target: '' })

function openEditNotification(ch: NotificationChannel) {
  editingNotification.value = ch
  notifForm.enabled = ch.enabled
  notifForm.target = ch.target
}

async function saveNotificationEdit() {
  if (!editingNotification.value) return
  saving.value = true
  error.value = ''
  try {
    await updateNotificationChannel(editingNotification.value.name, {
      enabled: notifForm.enabled,
      target: notifForm.target,
    })
    editingNotification.value = null
    showNotice('通知渠道已更新')
    await loadNotificationChannels()
  } catch (err: unknown) {
    error.value = errorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}

async function handleTestNotification(ch: NotificationChannel) {
  saving.value = true
  error.value = ''
  try {
    const result = await testNotificationChannel(ch.name)
    showNotice(result.message)
  } catch (err: unknown) {
    error.value = errorMessage(err, '测试失败')
  } finally {
    saving.value = false
  }
}

async function handleExportData() {
  showNotice('数据导出任务已提交')
}

async function handleCleanupData() {
  if (!window.confirm('确认清理过期数据？此操作不可撤销。')) return
  showNotice('数据清理任务已提交')
}

async function handleBackupData() {
  showNotice('数据备份任务已提交')
}

async function handleRestoreData() {
  if (!window.confirm('确认从备份恢复数据？当前数据将被覆盖。')) return
  showNotice('数据恢复任务已提交')
}

onMounted(async () => {
  await Promise.all([loadSettings(), loadRiskRules()])
  await Promise.all([loadModelServices(), loadUsers(), loadNotificationChannels(), loadAuditLogs()])
})

watch(activeTab, (tab) => {
  if (tab === '操作日志') loadAuditLogs()
  if (tab === '用户管理') loadUsers()
  if (tab === '模型设置') loadModelServices()
  if (tab === '通知设置') loadNotificationChannels()
})
</script>

<template>
  <section class="page-header settings-header">
    <div>
      <h1>设置管理中心</h1>
      <p>配置系统参数、模型服务、风险规则等</p>
    </div>
  </section>

  <div class="settings-layout settings-center">
    <div class="panel settings-tabs">
      <button
        v-for="tab in tabs"
        :key="tab"
        class="tab-button"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{ tab }}
      </button>
    </div>

    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="notice" class="success-banner">{{ notice }}</div>

    <!-- ==================== 系统设置 ==================== -->
    <section v-if="activeTab === '系统设置'" class="settings-section">
      <div class="section-title">
        <div>
          <h2>基础配置</h2>
          <p class="muted small">上次保存：{{ settingsUpdatedAt || '尚未保存' }}</p>
        </div>
        <button class="button" :disabled="saving" @click="saveSettings('基础配置已保存')">
          {{ saving ? '保存中...' : '保存设置' }}
        </button>
      </div>
      <div class="settings-form">
        <div class="settings-row"><label>系统名称</label><input v-model="systemConfig.name" class="input" /></div>
        <div class="settings-row"><label>系统描述</label><input v-model="systemConfig.description" class="input" /></div>
        <div class="settings-row"><label>时区设置</label><select v-model="systemConfig.timezone" class="select"><option>Asia/Shanghai (UTC+08:00)</option></select></div>
        <div class="settings-row"><label>日期格式</label><select v-model="systemConfig.dateFormat" class="select"><option>YYYY-MM-DD HH:mm:ss</option></select></div>
        <div class="settings-row"><label>语言设置</label><select v-model="systemConfig.language" class="select"><option>简体中文</option></select></div>
      </div>
      <div class="settings-subsection">
        <h2>服务配置</h2>
        <div class="service-config-grid">
          <div v-for="row in serviceCards" :key="row.name" class="service-config-card">
            <span class="service-config-icon" :class="`service-icon-${serviceIconName(row.name)}`">
              <img :src="`/service-icons/${serviceIconName(row.name)}.svg`" alt="" />
            </span>
            <div>
              <strong>{{ row.name }}</strong>
              <span>{{ row.endpoint }}</span>
            </div>
            <span class="status-ok">● {{ row.status }}</span>
            <button class="button secondary service-config-button" @click="activeTab = '模型设置'">配置</button>
          </div>
        </div>
      </div>
    </section>

    <!-- ==================== 模型设置 ==================== -->
    <section v-else-if="activeTab === '模型设置'" class="settings-section model-service-section">
      <div class="section-title model-service-title">
        <div>
          <h2>模型服务配置</h2>
          <p class="muted small">配置风险分析所使用的模型与服务</p>
        </div>
        <div class="toolbar">
          <button class="button secondary" :disabled="saving" @click="testModel('模型集群')">
            {{ testingModel === '模型集群' ? '测试中...' : '模型连通性测试' }}
          </button>
          <button class="button" @click="openAddModel">+ 新增模型</button>
        </div>
      </div>
      <div class="table-wrap model-service-table">
        <table>
          <thead>
            <tr>
              <th>模型名称</th>
              <th>模型类型</th>
              <th>服务方式</th>
              <th>模型/服务地址</th>
              <th>状态</th>
              <th>默认模型</th>
              <th>更新时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in modelServices" :key="row.name">
              <td>{{ row.name }}</td>
              <td>{{ row.type }}</td>
              <td>{{ row.deployment }}</td>
              <td>{{ row.endpoint }}</td>
              <td><span class="status-ok model-running">● {{ row.status }}</span></td>
              <td>{{ row.default ? '是' : '否' }}</td>
              <td>{{ row.updatedAt }}</td>
              <td>
                <div class="table-actions">
                  <button class="button-link table-action" @click="openEditModel(row)">编辑</button>
                  <button class="button-link table-action" @click="testModel(row.name)">
                    {{ testingModel === row.name ? '测试中' : '测试' }}
                  </button>
                  <button class="link-danger" @click="handleDeleteModel(row)">删除</button>
                </div>
              </td>
            </tr>
            <tr v-if="!modelServices.length">
              <td colspan="8" class="muted">暂无模型服务</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="settings-subsection">
        <h2>模型参数配置（本地大模型）</h2>
        <div class="model-param-grid">
          <label>最大输出长度 <input v-model.number="modelParams.maxTokens" class="input" /></label>
          <label>温度 <input v-model.number="modelParams.temperature" class="input" /></label>
          <label>Top P <input v-model.number="modelParams.topP" class="input" /></label>
          <label>重复惩罚 <input v-model.number="modelParams.repetitionPenalty" class="input" /></label>
          <label>超时时间（秒） <input v-model.number="modelParams.timeout" class="input" /></label>
          <label>并发数 <input v-model.number="modelParams.concurrency" class="input" /></label>
        </div>
        <div class="toolbar" style="justify-content: flex-end">
          <button class="button" :disabled="saving" @click="saveSettings('模型参数已保存')">
            {{ saving ? '保存中...' : '保存参数' }}
          </button>
        </div>
      </div>
    </section>

    <!-- ==================== 规则配置 ==================== -->
    <section v-else-if="activeTab === '规则配置'" class="settings-section settings-split">
      <aside class="settings-side-tabs">
        <button class="active">评分规则</button>
        <button>命中规则</button>
        <button>关键词规则</button>
        <button>名单规则</button>
        <button>处置规则</button>
      </aside>
      <div class="settings-main-pane">
        <div class="section-title">
          <div>
            <h2>风险评分规则</h2>
            <p class="muted small">配置多维度风险评分规则及权重</p>
          </div>
        </div>
        <div class="table-wrap settings-rule-table">
          <table>
            <thead>
              <tr>
                <th>维度名称</th>
                <th>权重</th>
                <th>评分规则说明</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in dimensionRows" :key="row.key">
                <td>{{ row.name }}</td>
                <td>{{ Number(row.weight).toFixed(2) }}</td>
                <td>{{ row.desc }}</td>
                <td><span class="status-ok">启用</span></td>
                <td>
                  <button class="button-link table-action" @click="copyRule(row)">复制</button>
                  <button class="link-danger" style="margin-left: 18px" @click="resetRule(row.key)">重置</button>
                </td>
              </tr>
            </tbody>
            <tfoot>
              <tr>
                <td colspan="4">权重总和：{{ totalWeight }}　更新时间：{{ updatedAt || '未保存' }}</td>
                <td style="text-align: right">
                  <button class="button" :disabled="saving" @click="saveRiskRules">{{ saving ? '保存中...' : '保存权重' }}</button>
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      </div>
    </section>

    <!-- ==================== 用户管理 ==================== -->
    <section v-else-if="activeTab === '用户管理'" class="settings-section settings-split">
      <aside class="settings-side-tabs">
        <button class="active">全部用户 <strong>{{ users.length }}</strong></button>
        <button v-for="(count, role) in userRoleCounts" :key="role">{{ role }} <strong>{{ count }}</strong></button>
      </aside>
      <div class="settings-main-pane">
        <div class="section-title">
          <h2>用户列表</h2>
          <button class="button" @click="openAddUser">+ 新增用户</button>
        </div>
        <label class="search-field settings-search">
          <input v-model="userSearch" class="input" placeholder="搜索用户名/姓名" />
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" /></svg>
        </label>
        <div class="table-wrap">
          <table>
            <thead><tr><th>用户名</th><th>姓名</th><th>角色</th><th>状态</th><th>最后登录时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="row in filteredUsers" :key="row.username">
                <td>{{ row.username }}</td>
                <td>{{ row.name }}</td>
                <td>{{ row.role }}</td>
                <td><span :class="row.status === '启用' ? 'status-ok' : 'muted'">{{ row.status }}</span></td>
                <td>{{ row.lastLogin || '-' }}</td>
                <td>
                  <button class="button-link table-action" @click="openEditUser(row)">编辑</button>
                  <button class="button-link table-action" style="margin-left: 16px" @click="handleResetPassword(row)">重置密码</button>
                  <button
                    class="link-danger"
                    style="margin-left: 16px"
                    @click="handleToggleUser(row)"
                  >{{ row.status === '启用' ? '禁用' : '启用' }}</button>
                  <button class="link-danger" style="margin-left: 16px" @click="handleDeleteUser(row)">删除</button>
                </td>
              </tr>
              <tr v-if="!filteredUsers.length">
                <td colspan="6" class="muted">{{ userSearch ? '无匹配用户' : '暂无用户' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <!-- ==================== 操作日志 ==================== -->
    <section v-else-if="activeTab === '操作日志'" class="settings-section">
      <div class="settings-filterbar">
        <select v-model="auditFilterAction" class="select">
          <option value="">全部动作</option>
          <option value="settings.update">设置更新</option>
          <option value="risk_rules.update">规则更新</option>
          <option value="user.create">用户创建</option>
          <option value="user.update">用户更新</option>
          <option value="user.delete">用户删除</option>
          <option value="model_service">模型服务</option>
          <option value="notification">通知渠道</option>
        </select>
        <input v-model="auditFilterActor" class="input" placeholder="操作人" />
        <input v-model="auditFilterDateFrom" class="input" type="date" />
        <input v-model="auditFilterDateTo" class="input" type="date" />
        <button class="button" :disabled="auditLoading" @click="auditPage = 1; loadAuditLogs()">查询</button>
      </div>
      <div class="table-wrap">
        <table>
          <thead><tr><th>时间</th><th>操作人</th><th>动作</th><th>资源</th><th>详情</th></tr></thead>
          <tbody>
            <tr v-for="row in auditLogs" :key="row.id">
              <td class="small muted">{{ row.created_at }}</td>
              <td>{{ row.actor }} / {{ row.role }}</td>
              <td>{{ row.action }}</td>
              <td>{{ row.resource_type }} {{ row.resource_id || '' }}</td>
              <td class="small muted">{{ JSON.stringify(row.detail || {}) }}</td>
            </tr>
            <tr v-if="!auditLogs.length">
              <td colspan="5" class="muted">{{ auditLoading ? '加载中...' : '暂无审计日志' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="pagination">
        <span class="muted small">共 {{ auditTotal }} 条</span>
        <button
          class="button secondary pager-button"
          :disabled="auditPage <= 1"
          @click="auditPage--; loadAuditLogs()"
        >上一页</button>
        <span class="page-number">{{ auditPage }}</span>
        <button
          class="button secondary pager-button"
          :disabled="auditPage * 50 >= auditTotal"
          @click="auditPage++; loadAuditLogs()"
        >下一页</button>
      </div>
    </section>

    <!-- ==================== 数据管理 ==================== -->
    <section v-else-if="activeTab === '数据管理'" class="settings-section settings-split">
      <aside class="settings-side-tabs">
        <button class="active">事件数据 <strong>{{ dataManagement.summary[0]?.value || '0' }}</strong></button>
      </aside>
      <div class="settings-main-pane">
        <h2>事件数据</h2>
        <div class="data-summary">
          <span v-for="item in dataManagement.summary" :key="item.label">{{ item.label }}<strong>{{ item.value }}</strong></span>
        </div>
        <h2>数据管理</h2>
        <div class="toolbar">
          <button class="button secondary" @click="handleExportData">导出数据</button>
          <button class="button danger" @click="handleCleanupData">清理数据</button>
          <button class="button secondary" @click="handleBackupData">数据备份</button>
          <button class="button secondary" @click="handleRestoreData">数据恢复</button>
        </div>
        <h2>自动清理策略</h2>
        <div class="settings-row"><label>保留最近</label><select v-model.number="dataManagement.retentionDays" class="select"><option :value="90">90 天</option><option :value="180">180 天</option><option :value="365">365 天</option></select></div>
        <div class="settings-row"><label>定时执行</label><select v-model="dataManagement.cleanupTime" class="select"><option>每日 02:00</option><option>每日 03:00</option><option>每周日 02:00</option></select></div>
        <label class="switch-row"><input v-model="dataManagement.cleanupEnabled" type="checkbox" /> 启用</label>
        <div class="toolbar" style="justify-content: flex-end">
          <button class="button" :disabled="saving" @click="saveSettings('数据管理配置已保存')">保存配置</button>
        </div>
      </div>
    </section>

    <!-- ==================== 通知设置 ==================== -->
    <section v-else class="settings-section">
      <h2>通知渠道配置</h2>
      <div class="notification-list">
        <div v-for="row in notificationChannels" :key="row.name" class="notification-row">
          <span class="service-config-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v12H4zM4 7l8 6 8-6" /></svg>
          </span>
          <strong>{{ row.name }}</strong>
          <span :class="row.enabled ? 'status-ok' : 'muted'">{{ row.enabled ? '已启用' : '停用' }}</span>
          <template v-if="editingNotification?.name === row.name">
            <label style="margin-left: 8px">
              <input v-model="notifForm.enabled" type="checkbox" /> 启用
            </label>
            <input v-model="notifForm.target" class="input" style="width: 200px; margin-left: 8px" placeholder="目标地址" />
            <button class="button-link table-action" style="margin-left: 8px" @click="saveNotificationEdit">保存</button>
            <button class="button-link table-action" @click="editingNotification = null">取消</button>
          </template>
          <template v-else>
            <span>{{ row.target }}</span>
            <button class="button-link table-action" @click="openEditNotification(row)">编辑</button>
            <button class="button-link table-action" @click="handleTestNotification(row)">测试</button>
          </template>
        </div>
      </div>
      <h2>通知事件配置</h2>
      <div class="notify-check-grid">
        <label v-for="item in notificationEvents" :key="item">
          <input type="checkbox" :checked="isEventEnabled(item)" @change="toggleEvent(item)" /> {{ item }}
        </label>
      </div>
      <div class="toolbar" style="justify-content: flex-end">
        <button class="button" :disabled="saving" @click="saveSettings('通知配置已保存')">保存配置</button>
      </div>
    </section>
  </div>

  <!-- ==================== 模型服务编辑弹窗 ==================== -->
  <Teleport to="body">
    <div v-if="showModelDialog" class="modal-overlay" @click.self="showModelDialog = false">
      <div class="modal-panel">
        <h2>{{ editingModel ? '编辑模型服务' : '新增模型服务' }}</h2>
        <div class="settings-form" style="margin-top: 16px">
          <div class="settings-row"><label>模型名称</label><input v-model="modelForm.name" class="input" :disabled="!!editingModel" /></div>
          <div class="settings-row"><label>模型类型</label><input v-model="modelForm.type" class="input" placeholder="如：大语言模型" /></div>
          <div class="settings-row"><label>服务方式</label><input v-model="modelForm.deployment" class="input" /></div>
          <div class="settings-row"><label>服务地址</label><input v-model="modelForm.endpoint" class="input" placeholder="http://localhost:8001/v1" /></div>
          <div class="settings-row"><label>默认模型</label><select v-model="modelForm.default" class="select"><option :value="true">是</option><option :value="false">否</option></select></div>
        </div>
        <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
          <button class="button secondary" @click="showModelDialog = false">取消</button>
          <button class="button" :disabled="saving" @click="submitModelForm">{{ saving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </Teleport>

  <!-- ==================== 用户编辑弹窗 ==================== -->
  <Teleport to="body">
    <div v-if="showUserDialog" class="modal-overlay" @click.self="showUserDialog = false">
      <div class="modal-panel">
        <h2>{{ editingUser ? '编辑用户' : '新增用户' }}</h2>
        <div class="settings-form" style="margin-top: 16px">
          <div class="settings-row"><label>用户名</label><input v-model="userForm.username" class="input" :disabled="!!editingUser" /></div>
          <div class="settings-row"><label>姓名</label><input v-model="userForm.name" class="input" /></div>
          <div class="settings-row">
            <label>角色</label>
            <select v-model="userForm.role" class="select">
              <option>超级管理员</option>
              <option>风控管理员</option>
              <option>审核人员</option>
              <option>普通用户</option>
            </select>
          </div>
          <div v-if="!editingUser" class="settings-row"><label>初始密码</label><input v-model="userForm.password" class="input" type="password" placeholder="不填则使用默认密码" /></div>
        </div>
        <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
          <button class="button secondary" @click="showUserDialog = false">取消</button>
          <button class="button" :disabled="saving" @click="submitUserForm">{{ saving ? '保存中...' : '保存' }}</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-panel {
  background: var(--panel);
  border-radius: 12px;
  padding: 24px;
  min-width: 420px;
  max-width: 560px;
  box-shadow: var(--shadow);
}
.modal-panel h2 {
  margin: 0;
}
</style>
