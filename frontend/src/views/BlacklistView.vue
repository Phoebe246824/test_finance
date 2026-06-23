<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
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
const searchText = ref('')
const editorOpen = ref(false)
const editorMode = ref<'create' | 'edit'>('create')

const activeLabel = computed(() => tabs.find((tab) => tab.key === active.value)?.label || '黑名单')
function personId(item: any) {
  return String(item.value || '').split(/[｜|,，\s]+/)[0] || '-'
}

function personName(item: any) {
  const value = String(item.value || '')
  const parts = value.split(/[｜|,，\s]+/).filter(Boolean)
  if (parts.length > 1) return parts.slice(1).join(' ')
  return item.summary || item.description || '-'
}

const filteredItems = computed(() => {
  const keyword = searchText.value.trim().toLowerCase()
  if (!keyword) return items.value
  return items.value.filter((item) =>
    [item.value, item.summary, item.description].some((value) =>
      String(value || '').toLowerCase().includes(keyword),
    ),
  )
})

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
    editorOpen.value = false
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
  editorMode.value = 'edit'
  editorOpen.value = true
}

function clearForm() {
  editingValue.value = ''
  value.value = ''
  summary.value = ''
  description.value = ''
}

function openCreate() {
  clearForm()
  editorMode.value = 'create'
  editorOpen.value = true
}

async function switchTab(key: BlacklistType) {
  active.value = key
  clearForm()
  editorOpen.value = false
  await load()
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>黑名单管理</h1>
      <p>维护人员、关键词和高危事件样本。</p>
    </div>
  </section>

  <div class="panel stack blacklist-prototype">
      <div class="blacklist-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="tab-button"
          :class="{ active: active === tab.key }"
          @click="switchTab(tab.key)"
        >
          {{ tab.label }}
        </button>
      </div>

      <div class="blacklist-toolbar">
        <label class="search-field">
          <input v-model="searchText" class="input" :placeholder="active === 'persons' ? '搜索人员' : active === 'keywords' ? '搜索关键词' : '搜索样本'" />
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="m21 21-4.3-4.3M10.8 18a7.2 7.2 0 1 1 0-14.4 7.2 7.2 0 0 1 0 14.4Z" />
          </svg>
        </label>
        <button class="button" @click="openCreate">
          {{ active === 'persons' ? '新增人员' : active === 'keywords' ? '新增关键词' : '新增样本' }}
        </button>
      </div>

      <div class="blacklist-table-shell">
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <template v-if="active === 'persons'">
                  <th>值（人员ID/名称）</th>
                  <th>摘要</th>
                  <th>说明</th>
                </template>
                <template v-else>
                  <th>值</th>
                  <th>摘要</th>
                  <th>说明</th>
                </template>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in filteredItems" :key="item.id">
                <template v-if="active === 'persons'">
                  <td><strong>{{ personId(item) }}</strong>　{{ personName(item) }}</td>
                  <td>{{ item.summary || item.description || '无摘要' }}</td>
                  <td>{{ item.description || '无说明' }}</td>
                </template>
                <template v-else>
                  <td><strong>{{ item.value }}</strong></td>
                  <td>{{ item.summary || '无摘要' }}</td>
                  <td>{{ item.description || '无说明' }}</td>
                </template>
                <td><span class="status-ok">{{ item.enabled ? '启用' : '停用' }}</span></td>
                <td>
                  <div class="table-actions">
                    <button class="table-action button-link" @click="editItem(item)">编辑</button>
                    <button class="link-danger" @click="removeItem(item.value)">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!filteredItems.length">
                <td colspan="5" class="muted">暂无数据</td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="pagination">
          <span class="muted small">共 {{ filteredItems.length }} 条</span>
          <button class="button secondary pager-button" disabled>‹</button>
          <span class="page-number">1</span>
          <button class="button secondary pager-button" disabled>›</button>
        </div>
      </div>
      <div v-if="error" class="error">{{ error }}</div>
  </div>

  <div v-if="editorOpen" class="modal-backdrop" @click.self="editorOpen = false">
    <div class="modal-panel blacklist-modal">
      <div class="section-title">
        <h2>{{ editorMode === 'edit' ? '编辑条目' : '新增条目' }}</h2>
        <button class="button secondary icon-refresh" @click="editorOpen = false">×</button>
      </div>
      <template v-if="active === 'persons'">
        <div class="field">
          <label>人员ID</label>
          <input v-model="value" class="input" placeholder="请输入内容" />
        </div>
        <div class="field">
          <label>名称</label>
          <input v-model="summary" class="input" placeholder="可选" />
        </div>
        <div class="field">
          <label>说明</label>
          <textarea v-model="description" class="textarea compact-textarea" />
        </div>
      </template>
      <template v-else>
        <div class="field">
          <label>名称</label>
          <input v-model="value" class="input" placeholder="请输入内容" />
        </div>
        <div class="field">
          <label>摘要</label>
          <input v-model="summary" class="input" placeholder="可选" />
        </div>
        <div class="field">
          <label>说明</label>
          <textarea v-model="description" class="textarea compact-textarea" />
        </div>
      </template>
      <div class="toolbar">
        <button class="button" :disabled="saving || !value.trim()" @click="addItem">
          {{ editorMode === 'edit' ? '保存修改' : '确认新增' }}
        </button>
        <button class="button secondary" @click="editorOpen = false">取消</button>
      </div>
    </div>
  </div>
</template>
