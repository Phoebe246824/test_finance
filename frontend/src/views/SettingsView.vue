<script setup lang="ts">
import { ref } from 'vue'
import AuditLogTab from './settings/AuditLogTab.vue'
import DataManagementTab from './settings/DataManagementTab.vue'
import ModelSettingsTab from './settings/ModelSettingsTab.vue'
import NotificationSettingsTab from './settings/NotificationSettingsTab.vue'
import RiskRulesTab from './settings/RiskRulesTab.vue'
import RuntimeConfigTab from './settings/RuntimeConfigTab.vue'
import SystemSettingsTab from './settings/SystemSettingsTab.vue'

const tabs = ['系统设置', '模型设置', '规则配置', '完整配置', '操作日志', '数据管理', '通知设置'] as const
type SettingsTab = (typeof tabs)[number]

const activeTab = ref<SettingsTab>('系统设置')
const notice = ref('')
const error = ref('')

function showNotice(message: string): void {
  notice.value = message
  error.value = ''
  window.setTimeout(() => {
    if (notice.value === message) notice.value = ''
  }, 2400)
}

function showError(message: string): void {
  error.value = message
  notice.value = ''
}

function navigate(tab: string): void {
  if (tabs.includes(tab as SettingsTab)) {
    activeTab.value = tab as SettingsTab
  }
}
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

    <SystemSettingsTab
      v-if="activeTab === '系统设置'"
      @notice="showNotice"
      @error="showError"
      @navigate="navigate"
    />
    <ModelSettingsTab
      v-else-if="activeTab === '模型设置'"
      @notice="showNotice"
      @error="showError"
    />
    <RiskRulesTab
      v-else-if="activeTab === '规则配置'"
      @notice="showNotice"
      @error="showError"
    />
    <RuntimeConfigTab
      v-else-if="activeTab === '完整配置'"
      @notice="showNotice"
      @error="showError"
    />
    <AuditLogTab
      v-else-if="activeTab === '操作日志'"
      @error="showError"
    />
    <DataManagementTab
      v-else-if="activeTab === '数据管理'"
      @notice="showNotice"
      @error="showError"
    />
    <NotificationSettingsTab
      v-else
      @notice="showNotice"
      @error="showError"
    />
  </div>
</template>
