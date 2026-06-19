<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { createBlacklistItem, deleteBlacklistItem, listBlacklist, type BlacklistType } from '../api/blacklist'

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

async function load() {
  const data = await listBlacklist(active.value)
  items.value = data.items || []
}

async function addItem() {
  if (!value.value.trim()) return
  await createBlacklistItem(active.value, {
    value: value.value.trim(),
    summary: summary.value.trim(),
    description: description.value.trim(),
  })
  value.value = ''
  summary.value = ''
  description.value = ''
  await load()
}

async function removeItem(itemValue: string) {
  await deleteBlacklistItem(active.value, itemValue)
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
          @click="active = tab.key; load()"
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
      <button class="button" @click="addItem">新增</button>
      <div v-if="error" class="error">{{ error }}</div>
    </div>

    <div class="panel stack">
      <h2>当前列表</h2>
      <div v-for="item in items" :key="item.id" class="metric">
        <div class="toolbar" style="justify-content: space-between">
          <strong>{{ item.value }}</strong>
          <button class="button danger" @click="removeItem(item.value)">删除</button>
        </div>
        <p class="muted small">{{ item.summary || item.description || '无摘要' }}</p>
      </div>
      <p v-if="!items.length" class="muted">暂无数据</p>
    </div>
  </div>
</template>
