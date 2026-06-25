<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { getAppSettings, updateSystemConfig, type ModelService, type SystemConfig } from '../../api/settings'
import { useAppSettingsStore } from '../../stores/appSettings'
import { defaultSystemConfig, errorMessage } from './helpers'

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
  navigate: [tab: string]
}>()

const saving = ref(false)
const appSettings = useAppSettingsStore()
const updatedAt = ref('')
const systemConfig = reactive<SystemConfig>({ ...defaultSystemConfig })
const loaded = ref(false)
const modelServices = ref<ModelService[]>([])

const serviceFallbacks: ModelService[] = [
  { name: 'API 服务', type: '后端接口', deployment: '本地部署', endpoint: 'http://localhost:8000', status: '正常', default: true, updatedAt: '' },
  { name: 'Milvus 向量库', type: '向量数据库', deployment: 'Docker Compose', endpoint: 'http://localhost:19530', status: '正常', default: false, updatedAt: '' },
  { name: 'Neo4j 图数据库', type: '图数据库', deployment: 'Docker Compose', endpoint: 'bolt://localhost:7687', status: '正常', default: false, updatedAt: '' },
  { name: 'LLM 大模型服务', type: '大语言模型', deployment: '本地部署', endpoint: '本地模型（Qwen3-8B）', status: '正常', default: false, updatedAt: '' },
]

const serviceCards = computed(() =>
  serviceFallbacks.map((fallback) => modelServices.value.find((item) => item.name === fallback.name) || fallback),
)

function serviceIconName(name: string): string {
  if (name.includes('Milvus')) return 'milvus'
  if (name.includes('Neo4j')) return 'neo4j'
  if (name.includes('LLM') || name.includes('模型')) return 'llm'
  return 'api'
}

async function load(): Promise<void> {
  try {
    const data = await getAppSettings()
    loaded.value = true
    Object.assign(systemConfig, data.settings.system_config || defaultSystemConfig)
    modelServices.value = data.settings.model_services || []
    updatedAt.value = data.updated_at
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载设置失败'))
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    if (!loaded.value) {
      emit('error', '配置尚未加载完成')
      return
    }
    const saved = await updateSystemConfig({ ...systemConfig })
    appSettings.applySystemConfig(saved.settings.system_config)
    Object.assign(systemConfig, saved.settings.system_config || defaultSystemConfig)
    updatedAt.value = saved.updated_at
    emit('notice', '基础配置已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="settings-section">
    <div class="section-title">
      <div>
        <h2>基础配置</h2>
        <p class="muted small">上次保存：{{ updatedAt || '尚未保存' }}</p>
      </div>
      <button class="button" :disabled="saving || !loaded" @click="save">
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
          <button
            v-if="row.type.includes('模型')"
            class="button secondary service-config-button"
            @click="emit('navigate', '模型设置')"
          >
            配置
          </button>
        </div>
      </div>
    </div>
  </section>
</template>
