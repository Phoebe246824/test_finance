<script setup lang="ts">
import { onMounted, ref } from 'vue'
import {
  createBlacklistItem,
  deleteBlacklistItem,
  listBlacklist,
  updateBlacklistItem,
  type BlacklistType,
} from '../api/blacklist'

const tabs: { key: BlacklistType; label: string }[] = [
  { key: 'persons', label: '人员黑名单' },
  { key: 'keywords', label: '关键词黑名单' },
  { key: 'events', label: '高危事件黑名单' },
]

const active = ref<BlacklistType>('persons')
const items = ref<any[]>([])
const value = ref('')
const summary = ref('')
const description = ref('')
const error = ref('')
const editingValue = ref('')
const saving = ref(false)

async function load() {
  error.value = ''
  try {
    const data = await listBlacklist(active.value)
    items.value = data.items || []
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '加载黑名单失败'
  }
}

async function addItem() {
  if (!value.value.trim()) return
  saving.value = true
  error.value = ''
  const payload = {
    value: value.value.trim(),
    summary: summary.value.trim(),
    description: description.value.trim(),
  }
  try {
    if (editingValue.value) {
      await updateBlacklistItem(active.value, editingValue.value, payload)
    } else {
      await createBlacklistItem(active.value, payload)
    }
    clearForm()
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '保存失败'
  } finally {
    saving.value = false
  }
}

async function removeItem(itemValue: string) {
  error.value = ''
  try {
    await deleteBlacklistItem(active.value, itemValue)
    if (editingValue.value === itemValue) clearForm()
    await load()
  } catch (err: any) {
    error.value = err?.response?.data?.detail || err?.message || '删除失败'
  }
}

function editItem(item: any) {
  editingValue.value = item.value
  value.value = item.value || ''
  summary.value = item.summary || ''
  description.value = item.description || ''
}

function clearForm() {
  editingValue.value = ''
  value.value = ''
  summary.value = ''
  description.value = ''
}

async function switchTab(key: BlacklistType) {
  active.value = key
  clearForm()
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>黑名单</h1>
      <p>维护人员、关键词和高危事件样本。</p>
    </div>
  </section>

  <div class="blacklist-layout">
    <div class="panel blacklist-form">
      <div class="toolbar">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="button secondary"
          :class="{ active: active === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="field">
        <label>值</label>
        <input v-model="value" class="input" :placeholder="active === 'events' ? '事件ID或关键标识' : '请输入内容'" />
      </div>
      <div class="field">
        <label>摘要</label>
        <input v-model="summary" class="input" placeholder="可选" />
      </div>
      <div class="field">
        <label>说明</label>
        <textarea v-model="description" class="textarea compact-textarea" />
      </div>
      <div class="toolbar">
        <button class="button" :disabled="saving || !value.trim()" @click="addItem">
          {{ editingValue ? '保存修改' : '新增' }}
        </button>
        <button v-if="editingValue" class="button secondary" :disabled="saving" @click="clearForm">取消编辑</button>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="panel stack blacklist-list-panel">
      <h2>当前列表</h2>
      <div class="scroll-panel blacklist-items">
        <div v-for="item in items" :key="item.id" class="metric">
          <div class="toolbar" style="justify-content: space-between">
            <strong>{{ item.value }}</strong>
            <div class="toolbar">
              <button class="button secondary" @click="editItem(item)">编辑</button>
              <button class="button danger" @click="removeItem(item.value)">删除</button>
            </div>
          </div>
          <p class="muted small">{{ item.summary || item.description || '无摘要' }}</p>
        </div>
        <p v-if="!items.length" class="muted">暂无数据</p>
      </div>
    </div>
  </div>
</template>
