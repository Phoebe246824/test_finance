<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  listNotificationChannels,
  testNotificationChannel,
  updateNotificationChannel,
  type NotificationChannel,
} from '../../api/notifications'
import { getAppSettings, updateNotificationEvents } from '../../api/settings'
import { defaultNotificationEvents, errorMessage, notificationTestFeedback } from './helpers'

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
}>()

const saving = ref(false)
const channels = ref<NotificationChannel[]>([])
const loaded = ref(false)
const notificationEvents = ref([...defaultNotificationEvents])
const enabledEvents = ref(new Set<string>(defaultNotificationEvents))
const editingNotification = ref<NotificationChannel | null>(null)
const notifForm = reactive({ enabled: true, target: '' })

async function load(): Promise<void> {
  try {
    const [channelData, settingsData] = await Promise.all([
      listNotificationChannels(),
      getAppSettings(),
    ])
    channels.value = [...channelData.channels]
    loaded.value = true
    notificationEvents.value = [...defaultNotificationEvents]
    enabledEvents.value = new Set(settingsData.settings.notification_events || defaultNotificationEvents)
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载通知配置失败'))
  }
}

function isEventEnabled(event: string): boolean {
  return enabledEvents.value.has(event)
}

function toggleEvent(event: string): void {
  const next = new Set(enabledEvents.value)
  if (next.has(event)) {
    next.delete(event)
  } else {
    next.add(event)
  }
  enabledEvents.value = next
}

function openEditNotification(channel: NotificationChannel): void {
  editingNotification.value = channel
  notifForm.enabled = channel.enabled
  notifForm.target = channel.target
}

async function saveNotificationEdit(): Promise<void> {
  if (!editingNotification.value) return
  saving.value = true
  try {
    await updateNotificationChannel(editingNotification.value.name, {
      enabled: notifForm.enabled,
      target: notifForm.target,
    })
    editingNotification.value = null
    emit('notice', '通知渠道已更新')
    await load()
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存通知渠道失败'))
  } finally {
    saving.value = false
  }
}

async function handleTestNotification(channel: NotificationChannel): Promise<void> {
  saving.value = true
  try {
    const result = await testNotificationChannel(channel.name)
    const feedback = notificationTestFeedback(result)
    if (feedback.kind === 'notice') {
      emit('notice', feedback.message)
      return
    }
    emit('error', feedback.message)
  } catch (err: unknown) {
    emit('error', errorMessage(err, '测试通知渠道失败'))
  } finally {
    saving.value = false
  }
}

async function saveEvents(): Promise<void> {
  saving.value = true
  try {
    if (!loaded.value) {
      emit('error', '配置尚未加载完成')
      return
    }
    const saved = await updateNotificationEvents(Array.from(enabledEvents.value))
    enabledEvents.value = new Set(saved.settings.notification_events || defaultNotificationEvents)
    emit('notice', '通知配置已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存通知配置失败'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <section class="settings-section">
    <h2>通知渠道配置</h2>
    <div class="notification-list">
      <div v-for="row in channels" :key="row.name" class="notification-row">
        <span class="service-config-icon">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16v12H4zM4 7l8 6 8-6" /></svg>
        </span>
        <strong>{{ row.name }}</strong>
        <span :class="row.enabled ? 'status-ok' : 'muted'">{{ row.enabled ? '已启用' : '停用' }}</span>
        <template v-if="editingNotification?.name === row.name">
          <label class="inline-check">
            <input v-model="notifForm.enabled" type="checkbox" /> 启用
          </label>
          <input v-model="notifForm.target" class="input notification-target-input" placeholder="Webhook 地址" />
          <button class="button-link table-action" @click="saveNotificationEdit">保存</button>
          <button class="button-link table-action" @click="editingNotification = null">取消</button>
        </template>
        <template v-else>
          <span>{{ row.target }}</span>
          <button class="button-link table-action" @click="openEditNotification(row)">编辑</button>
          <button class="button-link table-action" @click="handleTestNotification(row)">校验</button>
        </template>
      </div>
      <div v-if="!channels.length" class="notification-row muted">暂无可用通知渠道</div>
    </div>
    <h2>通知事件配置</h2>
    <div class="notify-check-grid">
      <label v-for="item in notificationEvents" :key="item">
        <input type="checkbox" :checked="isEventEnabled(item)" @change="toggleEvent(item)" /> {{ item }}
      </label>
    </div>
    <div class="toolbar justify-end">
      <button class="button" :disabled="saving || !loaded" @click="saveEvents">保存配置</button>
    </div>
  </section>
</template>
