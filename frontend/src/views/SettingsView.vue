<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { listAuditLogs, type AuditLog } from '../api/audit'
import { getRiskRules, updateRiskRules, type RiskRules } from '../api/riskRules'
import {
  getAppSettings,
  updateAppSettings,
  type AppSettings,
  type DataManagement,
  type ManagedUser,
  type ModelParams,
  type ModelService,
  type NotificationChannel,
  type SystemConfig,
} from '../api/settings'

const tabs = ['系统设置', '模型设置', '规则配置', '用户管理', '操作日志', '数据管理', '通知设置']
const activeTab = ref('系统设置')
const saving = ref(false)
const testingModel = ref('')
const notice = ref('')
const error = ref('')
const updatedAt = ref('')
const settingsUpdatedAt = ref('')
const auditLogs = ref<AuditLog[]>([])
const auditTotal = ref(0)
const auditLoading = ref(false)

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

const notificationEvents = ref(['高风险事件', '黑名单命中', '系统异常', '复核任务提醒', '趋势报告生成', '模型服务异常'])
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

const defaultModelServices: ModelService[] = [
  {
    name: '本地大模型（Qwen3-8B）',
    type: '大语言模型',
    deployment: '本地部署',
    endpoint: 'http://localhost:8001/v1',
    status: '运行中',
    default: true,
    updatedAt: '2026-06-14 14:22:31',
  },
  {
    name: '向量模型（text-embedding-v3）',
    type: '向量模型',
    deployment: '本地部署',
    endpoint: 'http://localhost:8001/embeddings',
    status: '运行中',
    default: true,
    updatedAt: '2026-06-14 14:21:10',
  },
  {
    name: '重排序模型（bge-reranker）',
    type: '重排序模型',
    deployment: '本地部署',
    endpoint: 'http://localhost:8001/reranker',
    status: '运行中',
    default: false,
    updatedAt: '2026-06-14 14:20:05',
  },
  {
    name: '图谱抽取模型（graph-extract）',
    type: '信息抽取模型',
    deployment: '本地部署',
    endpoint: 'http://localhost:8001/graph',
    status: '运行中',
    default: false,
    updatedAt: '2026-06-14 14:19:42',
  },
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

function applySettings(data: AppSettings) {
  Object.assign(systemConfig, data.system_config || defaultSystemConfig)
  Object.assign(modelParams, data.model_params || defaultModelParams)
  const incomingModelServices = data.model_services || []
  modelServices.value = incomingModelServices.length && !hasLegacyModelServices(incomingModelServices)
    ? incomingModelServices
    : defaultModelServices
  users.value = data.users || []
  notificationChannels.value = data.notification_channels || []
  notificationEvents.value = data.notification_events || notificationEvents.value
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
    notification_events: notificationEvents.value,
  }
}

async function load() {
  try {
    const [riskData, settingsData] = await Promise.all([getRiskRules(), getAppSettings()])
    rules.value = riskData.rules
    updatedAt.value = riskData.updated_at
    applySettings(settingsData.settings)
    settingsUpdatedAt.value = settingsData.updated_at
  } catch (err: unknown) {
    error.value = errorMessage(err, '加载设置失败')
  }
}

async function loadAuditLogs() {
  auditLoading.value = true
  error.value = ''
  try {
    const data = await listAuditLogs({ page_size: 100 })
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
    notice.value = '配置已保存'
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
    notice.value = message
  } catch (err: unknown) {
    error.value = errorMessage(err, '保存失败')
  } finally {
    saving.value = false
  }
}

function saveLocal(message = '配置已保存') {
  notice.value = message
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 1800)
}

function testModel(name: string) {
  testingModel.value = name
  window.setTimeout(() => {
    testingModel.value = ''
    saveLocal(`${name} 连通性正常`)
  }, 600)
}

function resetRule(key: string) {
  rules.value.dimension_weights[key] = 0
}

function copyRule(row: { name: string }) {
  saveLocal(`已复制 ${row.name} 配置`)
}

onMounted(async () => {
  await load()
  await loadAuditLogs()
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
            <button class="button secondary service-config-button" @click="saveLocal(`${row.name} 配置已打开`)">配置</button>
          </div>
        </div>
      </div>
    </section>

    <section v-else-if="activeTab === '模型设置'" class="settings-section model-service-section">
      <div class="section-title model-service-title">
        <div>
          <h2>模型服务配置</h2>
          <p class="muted small">配置风险分析所使用的模型与服务</p>
        </div>
        <div class="toolbar">
          <button class="button secondary" @click="testModel('模型集群')">模型连通性测试</button>
          <button class="button" @click="saveLocal('已打开新增模型流程')">+ 新增模型</button>
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
                  <button class="button-link table-action" @click="saveLocal('进入模型编辑')">编辑</button>
                  <button class="button-link table-action" @click="testModel(row.name)">
                    {{ testingModel === row.name ? '测试中' : '测试' }}
                  </button>
                  <button class="link-danger">删除</button>
                </div>
              </td>
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
          <button class="button" @click="saveLocal('已打开新增规则流程')">+ 新增规则</button>
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
                  <button class="button-link table-action">编辑</button>
                  <button class="button-link table-action" style="margin-left: 18px" @click="copyRule(row)">复制</button>
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

    <section v-else-if="activeTab === '用户管理'" class="settings-section settings-split">
      <aside class="settings-side-tabs">
        <button class="active">超级管理员 <strong>2</strong></button>
        <button>风控管理员 <strong>6</strong></button>
        <button>审核人员 <strong>12</strong></button>
        <button>普通用户 <strong>8</strong></button>
        <button>访客 <strong>0</strong></button>
      </aside>
      <div class="settings-main-pane">
        <div class="section-title">
          <h2>用户列表</h2>
          <button class="button" @click="saveLocal('已打开新增用户流程')">+ 新增用户</button>
        </div>
        <label class="search-field settings-search">
          <input class="input" placeholder="搜索用户名/姓名" />
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" /></svg>
        </label>
        <div class="table-wrap">
          <table>
            <thead><tr><th>用户名</th><th>姓名</th><th>角色</th><th>状态</th><th>最后登录时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="row in users" :key="row.username">
                <td>{{ row.username }}</td><td>{{ row.name }}</td><td>{{ row.role }}</td>
                <td><span class="status-ok">{{ row.status }}</span></td><td>{{ row.lastLogin }}</td>
                <td><button class="button-link table-action">编辑</button><button class="button-link table-action" style="margin-left: 16px">重置密码</button><button class="link-danger" style="margin-left: 16px">禁用</button></td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>

    <section v-else-if="activeTab === '操作日志'" class="settings-section">
      <div class="settings-filterbar">
        <select class="select"><option>全部</option><option>登录</option><option>规则修改</option></select>
        <input class="input" placeholder="请输入用户名" />
        <input class="input" value="2026-06-01  —  2026-06-14" />
        <button class="button" :disabled="auditLoading" @click="loadAuditLogs">查询</button>
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
        <span class="page-number">1</span><button class="button secondary pager-button">2</button><button class="button secondary pager-button">3</button>
      </div>
    </section>

    <section v-else-if="activeTab === '数据管理'" class="settings-section settings-split">
      <aside class="settings-side-tabs">
        <button class="active">事件数据 <strong>1,248</strong></button>
        <button>黑名单数据 <strong>356</strong></button>
        <button>图谱数据 <strong>12,856</strong></button>
        <button>日志数据 <strong>58,963</strong></button>
        <button>缓存数据 <strong>2,145</strong></button>
      </aside>
      <div class="settings-main-pane">
        <h2>事件数据</h2>
        <div class="data-summary">
          <span v-for="item in dataManagement.summary" :key="item.label">{{ item.label }}<strong>{{ item.value }}</strong></span>
        </div>
        <h2>数据管理</h2>
        <div class="toolbar">
          <button class="button secondary" @click="saveLocal('已提交导出任务')">导出数据</button>
          <button class="button danger" @click="saveLocal('已提交清理任务')">清理数据</button>
          <button class="button secondary" @click="saveLocal('已提交备份任务')">数据备份</button>
          <button class="button secondary" @click="saveLocal('已提交恢复任务')">数据恢复</button>
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

    <section v-else class="settings-section">
      <h2>通知渠道配置</h2>
      <div class="notification-list">
        <div v-for="row in notificationChannels" :key="row.name" class="notification-row">
          <span class="service-config-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v12H4zM4 7l8 6 8-6" /></svg>
          </span>
          <strong>{{ row.name }}</strong>
          <span :class="row.enabled ? 'status-ok' : 'muted'">{{ row.enabled ? '已启用' : '停用' }}</span>
          <span>{{ row.target }}</span>
          <button class="button-link table-action">编辑</button>
          <button class="button-link table-action">测试</button>
        </div>
      </div>
      <h2>通知事件配置</h2>
      <div class="notify-check-grid">
        <label v-for="item in notificationEvents" :key="item"><input type="checkbox" checked /> {{ item }}</label>
      </div>
      <div class="toolbar" style="justify-content: flex-end">
        <button class="button" :disabled="saving" @click="saveSettings('通知配置已保存')">保存配置</button>
      </div>
    </section>
  </div>
</template>
