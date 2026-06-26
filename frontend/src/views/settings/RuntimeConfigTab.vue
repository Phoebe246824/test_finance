<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getAppSettings,
  updateAppSettings,
  type AppSettings,
  type RuntimeConfigField,
  type RuntimeConfigValue,
} from '../../api/settings'
import {
  buildConfigGroups,
  errorMessage,
  parseListEditorValue,
  serializeListEditorValue,
} from './helpers'
import './runtime-config.css'

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
}>()

type ListDrafts = Record<string, string>
type SecretRevealState = Record<string, boolean>

const loading = ref(false)
const saving = ref(false)
const loaded = ref(false)
const updatedAt = ref('')
const search = ref('')
const runtimeConfig = reactive<Record<string, RuntimeConfigValue>>({})
const runtimeConfigMetadata = ref<RuntimeConfigField[]>([])
const listDrafts = reactive<ListDrafts>({})
const revealSecret = reactive<SecretRevealState>({})
const settingsSnapshot = ref<AppSettings | null>(null)

const groups = computed(() =>
  buildConfigGroups(runtimeConfig, runtimeConfigMetadata.value, search.value),
)

function assignRuntimeConfig(nextConfig: Record<string, RuntimeConfigValue>): void {
  for (const key of Object.keys(runtimeConfig)) {
    delete runtimeConfig[key]
  }
  for (const [key, value] of Object.entries(nextConfig)) {
    runtimeConfig[key] = Array.isArray(value) ? [...value] : value
  }
}

function resetDrafts(): void {
  for (const key of Object.keys(listDrafts)) {
    delete listDrafts[key]
  }
  for (const field of runtimeConfigMetadata.value) {
    if (field.scalar_type === 'list') {
      const value = runtimeConfig[field.env]
      listDrafts[field.env] = serializeListEditorValue(Array.isArray(value) ? value : [])
    }
  }
}

function applySettingsPayload(settings: AppSettings, nextUpdatedAt: string): void {
  settingsSnapshot.value = settings
  runtimeConfigMetadata.value = [...settings.runtime_config_metadata]
  assignRuntimeConfig(settings.runtime_config)
  resetDrafts()
  updatedAt.value = nextUpdatedAt
  loaded.value = true
}

async function load(): Promise<void> {
  loading.value = true
  try {
    const data = await getAppSettings()
    applySettingsPayload(data.settings, data.updated_at)
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载完整配置失败'))
  } finally {
    loading.value = false
  }
}

function updateListValue(env: string, nextText: string): void {
  listDrafts[env] = nextText
  runtimeConfig[env] = parseListEditorValue(nextText)
}

function eventValue(event: Event): string {
  const target = event.target
  if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
    return target.value
  }
  return ''
}

function updateNumberValue(env: string, rawValue: string, field: RuntimeConfigField): void {
  if (rawValue.trim() === '') {
    runtimeConfig[env] = field.scalar_type === 'int' ? 0 : 0
    return
  }
  const parsed = Number(rawValue)
  if (Number.isNaN(parsed)) return
  runtimeConfig[env] = field.scalar_type === 'int' ? Math.trunc(parsed) : parsed
}

async function save(): Promise<void> {
  if (!settingsSnapshot.value) {
    emit('error', '配置尚未加载完成')
    return
  }
  saving.value = true
  try {
    const response = await updateAppSettings({
      ...settingsSnapshot.value,
      runtime_config: Object.fromEntries(
        Object.entries(runtimeConfig).map(([key, value]) => [
          key,
          Array.isArray(value) ? [...value] : value,
        ]),
      ),
      runtime_config_metadata: [...runtimeConfigMetadata.value],
    })
    applySettingsPayload(response.settings, response.updated_at)
    emit('notice', '完整配置已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存完整配置失败'))
  } finally {
    saving.value = false
  }
}

function fieldHint(field: RuntimeConfigField): string {
  return [field.env, field.help].filter(Boolean).join(' · ')
}

function toggleSecret(env: string): void {
  revealSecret[env] = !revealSecret[env]
}

onMounted(load)
</script>

<template>
  <section class="settings-section settings-split runtime-config-shell">
    <aside class="settings-side-tabs runtime-config-sidebar">
      <button class="active" type="button">
        <span>运行配置</span>
        <small>{{ groups.length }}</small>
      </button>
    </aside>

    <div class="settings-main-pane runtime-config-pane">
      <div class="section-title runtime-config-header">
        <div>
          <h2>完整配置</h2>
          <p class="muted small">上次保存：{{ updatedAt || '尚未保存' }}</p>
        </div>
        <div class="toolbar">
          <input
            v-model="search"
            class="input settings-search"
            type="search"
            placeholder="按分组、变量名或标签筛选"
          />
          <button class="button" :disabled="saving || loading || !loaded" @click="save">
            {{ saving ? '保存中...' : '保存配置' }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="runtime-config-state muted">正在加载配置...</div>
      <div v-else-if="!groups.length" class="runtime-config-state muted">
        未找到匹配项，请调整筛选条件。
      </div>

      <div v-else class="runtime-config-groups">
        <section
          v-for="group in groups"
          :key="group.group"
          class="settings-subsection runtime-config-group"
        >
          <div class="runtime-config-group-header">
            <div>
              <h3>{{ group.title }}</h3>
              <p class="muted small">{{ group.group }} · {{ group.matches }} 项</p>
            </div>
          </div>

          <div class="runtime-config-field-list">
            <div
              v-for="field in group.fields"
              :key="field.env"
              class="runtime-config-row"
              :class="{ 'is-readonly': !field.editable }"
            >
              <div class="runtime-config-copy">
                <label :for="field.env">{{ field.label }}</label>
                <p class="muted small">{{ fieldHint(field) }}</p>
              </div>

              <div class="runtime-config-control">
                <label
                  v-if="field.scalar_type === 'bool'"
                  class="switch-row runtime-bool-row"
                  :for="field.env"
                >
                  <input
                    :id="field.env"
                    v-model="runtimeConfig[field.env]"
                    type="checkbox"
                    :disabled="!field.editable"
                  />
                  <span>{{ runtimeConfig[field.env] ? '启用' : '关闭' }}</span>
                </label>

                <textarea
                  v-else-if="field.scalar_type === 'list'"
                  :id="field.env"
                  :value="listDrafts[field.env]"
                  class="input runtime-list-input"
                  :disabled="!field.editable"
                  rows="4"
                  @input="updateListValue(field.env, eventValue($event))"
                />

                <div v-else-if="field.secret" class="runtime-secret-input">
                  <input
                    :id="field.env"
                    :value="String(runtimeConfig[field.env] ?? '')"
                    class="input"
                    :disabled="!field.editable"
                    :type="revealSecret[field.env] ? 'text' : 'password'"
                    @input="runtimeConfig[field.env] = eventValue($event)"
                  />
                  <button
                    class="button secondary runtime-reveal-button"
                    type="button"
                    :disabled="!field.editable"
                    @click="toggleSecret(field.env)"
                  >
                    {{ revealSecret[field.env] ? '隐藏' : '显示' }}
                  </button>
                </div>

                <input
                  v-else-if="field.scalar_type === 'int' || field.scalar_type === 'float'"
                  :id="field.env"
                  :value="String(runtimeConfig[field.env] ?? '')"
                  class="input"
                  :disabled="!field.editable"
                  type="number"
                  step="any"
                  @input="updateNumberValue(field.env, eventValue($event), field)"
                />

                <input
                  v-else
                  :id="field.env"
                  v-model="runtimeConfig[field.env]"
                  class="input"
                  :disabled="!field.editable"
                  type="text"
                />

                <div class="runtime-meta-row">
                  <span class="runtime-scope-chip">{{ field.scopeLabel }}</span>
                  <span class="muted small">默认：{{ Array.isArray(field.default) ? field.default.join(', ') || '空' : String(field.default || '空') }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  </section>
</template>
