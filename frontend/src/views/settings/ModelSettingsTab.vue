<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  createModelService,
  deleteModelService,
  listModelServices,
  testModelService,
  testSavedModelService,
  updateModelService,
  type ModelService,
} from '../../api/modelServices'
import { getAppSettings, updateAppSettings, type AppSettings, type ModelParams } from '../../api/settings'
import { defaultModelParams, errorMessage, modelTestFeedback } from './helpers'
import ModelServiceDialog from './ModelServiceDialog.vue'

type ModelServiceFormPayload = {
  readonly name: string
  readonly type: string
  readonly deployment: string
  readonly endpoint: string
  readonly default: boolean
}

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
}>()

const saving = ref(false)
const testingModel = ref('')
const services = ref<ModelService[]>([])
const settings = ref<AppSettings | null>(null)
const modelParams = reactive<ModelParams>({ ...defaultModelParams })
const showDialog = ref(false)
const editingModel = ref<ModelService | null>(null)

async function load(): Promise<void> {
  try {
    const [serviceData, settingsData] = await Promise.all([
      listModelServices(),
      getAppSettings(),
    ])
    services.value = [...serviceData.services]
    settings.value = settingsData.settings
    Object.assign(modelParams, settingsData.settings.model_params || defaultModelParams)
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载模型设置失败'))
  }
}

async function testModel(name: string): Promise<void> {
  testingModel.value = name
  try {
    const targets = name === '模型集群' ? services.value : []
    if (!targets.length) {
      const response = await testSavedModelService(name)
      services.value = services.value.map((service) =>
        service.name === response.service.name ? response.service : service,
      )
      const feedback = modelTestFeedback(response.result)
      if (feedback.kind === 'notice') {
        emit('notice', feedback.message)
      } else {
        emit('error', feedback.message)
      }
      return
    }
    const results = await Promise.all(
      targets.map((service) => testModelService(service.endpoint, service.type)),
    )
    const failed = results.find((result) => !result.success)
    if (failed) {
      emit('error', modelTestFeedback(failed).message)
      return
    }
    const success = modelTestFeedback({
      success: true,
      message: name === '模型集群' ? '模型服务连接测试通过' : results[0].message,
    })
    emit('notice', success.message)
    await load()
  } catch (err: unknown) {
    emit('error', errorMessage(err, '模型连接测试失败'))
  } finally {
    testingModel.value = ''
  }
}

async function saveParams(): Promise<void> {
  saving.value = true
  try {
    const current = settings.value
    if (!current) {
      emit('error', '配置尚未加载完成')
      return
    }
    const saved = await updateAppSettings({
      ...current,
      model_params: { ...modelParams },
      model_services: services.value,
    })
    settings.value = saved.settings
    emit('notice', '模型参数已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存模型参数失败'))
  } finally {
    saving.value = false
  }
}

function openAddModel(): void {
  editingModel.value = null
  showDialog.value = true
}

function openEditModel(service: ModelService): void {
  editingModel.value = service
  showDialog.value = true
}

async function submitModelForm(payload: ModelServiceFormPayload): Promise<void> {
  if (!payload.name.trim() || !payload.type.trim() || !payload.endpoint.trim()) {
    emit('error', '请填写模型名称、类型和地址')
    return
  }
  saving.value = true
  try {
    if (editingModel.value) {
      await updateModelService(editingModel.value.name, {
        name: payload.name,
        type: payload.type,
        deployment: payload.deployment,
        endpoint: payload.endpoint,
        default: payload.default,
      })
      emit('notice', '模型服务已更新')
    } else {
      await createModelService({
        name: payload.name,
        type: payload.type,
        deployment: payload.deployment,
        endpoint: payload.endpoint,
        default: payload.default,
      })
      emit('notice', '模型服务已添加')
    }
    showDialog.value = false
    await load()
  } catch (err: unknown) {
    emit('error', errorMessage(err, '模型服务保存失败'))
  } finally {
    saving.value = false
  }
}

function modelStatusClass(status: string): string {
  if (status === '运行中') return 'status-ok'
  if (status === '异常') return 'status-danger'
  return 'status-muted'
}

async function handleDeleteModel(service: ModelService): Promise<void> {
  if (!window.confirm(`确认删除模型服务「${service.name}」？此操作不可撤销。`)) return
  saving.value = true
  try {
    await deleteModelService(service.name)
    emit('notice', `已删除模型服务「${service.name}」`)
    await load()
  } catch (err: unknown) {
    emit('error', errorMessage(err, '删除模型服务失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="settings-section model-service-section">
    <div class="section-title model-service-title">
      <div>
        <h2>模型服务配置</h2>
        <p class="muted small">配置风险分析所使用的模型与服务</p>
      </div>
      <div class="toolbar">
        <button class="button secondary" :disabled="saving" @click="testModel('模型集群')">
          {{ testingModel === '模型集群' ? '测试中...' : '模型连接测试' }}
        </button>
        <button class="button" @click="openAddModel">+ 新增模型</button>
      </div>
    </div>
    <div class="table-wrap model-service-table">
      <table>
        <thead>
          <tr>
            <th>模型名称</th><th>模型类型</th><th>服务方式</th><th>模型/服务地址</th>
            <th>状态</th><th>默认模型</th><th>更新时间</th><th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in services" :key="row.name">
            <td>{{ row.name }}</td>
            <td>{{ row.type }}</td>
            <td>{{ row.deployment }}</td>
            <td>{{ row.endpoint }}</td>
            <td><span :class="[modelStatusClass(row.status), 'model-running']">● {{ row.status }}</span></td>
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
          <tr v-if="!services.length">
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
        <label>重复惩罚（已接入） <input v-model.number="modelParams.repetitionPenalty" class="input" /></label>
        <label>超时时间（秒） <input v-model.number="modelParams.timeout" class="input" /></label>
        <label>并发数（队列预留） <input v-model.number="modelParams.concurrency" class="input" /></label>
      </div>
      <div class="toolbar justify-end">
        <button class="button" :disabled="saving || !settings" @click="saveParams">
          {{ saving ? '保存中...' : '保存参数' }}
        </button>
      </div>
    </div>
  </section>
  <ModelServiceDialog
    :open="showDialog"
    :editing-service="editingModel"
    :saving="saving"
    @close="showDialog = false"
    @submit="submitModelForm"
  />
</template>
