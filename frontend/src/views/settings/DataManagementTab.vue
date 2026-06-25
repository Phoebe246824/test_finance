<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  getAppSettings,
  runDataManagementCleanup,
  updateAppSettings,
  type AppSettings,
  type DataManagement,
} from '../../api/settings'
import { errorMessage } from './helpers'

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
}>()

const saving = ref(false)
const settings = ref<AppSettings | null>(null)
const dataManagement = reactive<DataManagement>({
  summary: [
    { label: '总记录数', value: '1,248' },
    { label: '数据大小', value: '128.6 MB' },
    { label: '最早记录', value: '2026-05-01' },
    { label: '最新记录', value: '2026-06-14' },
  ],
  retentionDays: 180,
})

async function load(): Promise<void> {
  try {
    const data = await getAppSettings()
    settings.value = data.settings
    Object.assign(dataManagement, data.settings.data_management || {})
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载数据管理配置失败'))
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const current = settings.value
    if (!current) {
      emit('error', '配置尚未加载完成')
      return
    }
    const saved = await updateAppSettings({
      ...current,
      data_management: {
        summary: dataManagement.summary,
        retentionDays: dataManagement.retentionDays,
      },
    })
    settings.value = saved.settings
    emit('notice', '数据管理配置已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存数据管理配置失败'))
  } finally {
    saving.value = false
  }
}

async function cleanup(): Promise<void> {
  if (!window.confirm('确认立即清理超过保留期的事件数据？此操作不可撤销。')) return
  saving.value = true
  try {
    const result = await runDataManagementCleanup()
    if (result.status === 'completed') {
      emit('notice', `清理完成，删除 ${result.deleted} 条过期事件`)
    } else {
      emit('notice', '清理未完成，请查看操作日志')
    }
  } catch (err: unknown) {
    emit('error', errorMessage(err, '清理失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="settings-section settings-split">
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
        <button class="button danger" :disabled="saving" @click="cleanup">清理数据</button>
      </div>
      <h2>清理策略</h2>
      <div class="settings-row"><label>保留最近</label><select v-model.number="dataManagement.retentionDays" class="select"><option :value="90">90 天</option><option :value="180">180 天</option><option :value="365">365 天</option></select></div>
      <div class="toolbar justify-end">
        <button class="button" :disabled="saving || !settings" @click="save">保存配置</button>
      </div>
    </div>
  </section>
</template>
