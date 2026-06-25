<script setup lang="ts">
import { reactive, watch } from 'vue'
import type { ModelService } from '../../api/modelServices'

type ModelServiceDialogPayload = {
  readonly name: string
  readonly type: string
  readonly deployment: string
  readonly endpoint: string
  readonly default: boolean
}

const props = defineProps<{
  readonly open: boolean
  readonly editingService: ModelService | null
  readonly saving: boolean
}>()

const emit = defineEmits<{
  close: []
  submit: [payload: ModelServiceDialogPayload]
}>()

const form = reactive({
  name: '',
  type: '',
  deployment: '本地部署',
  endpoint: '',
  default: false,
})

function resetForm(service: ModelService | null): void {
  form.name = service?.name || ''
  form.type = service?.type || ''
  form.deployment = service?.deployment || '本地部署'
  form.endpoint = service?.endpoint || ''
  form.default = service?.default || false
}

function submit(): void {
  emit('submit', {
    name: form.name,
    type: form.type,
    deployment: form.deployment,
    endpoint: form.endpoint,
    default: form.default,
  })
}

watch(
  () => props.open,
  (open) => {
    if (open) resetForm(props.editingService)
  },
)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-overlay" @click.self="emit('close')">
      <div class="modal-panel">
        <h2>{{ editingService ? '编辑模型服务' : '新增模型服务' }}</h2>
        <div class="settings-form modal-form">
          <div class="settings-row">
            <label for="model-name">模型名称</label>
            <input id="model-name" v-model="form.name" class="input" :disabled="!!editingService" />
          </div>
          <div class="settings-row">
            <label for="model-type">模型类型</label>
            <input id="model-type" v-model="form.type" class="input" placeholder="如：大语言模型" />
          </div>
          <div class="settings-row">
            <label for="model-deployment">服务方式</label>
            <input id="model-deployment" v-model="form.deployment" class="input" />
          </div>
          <div class="settings-row">
            <label for="model-endpoint">服务地址</label>
            <input id="model-endpoint" v-model="form.endpoint" class="input" placeholder="http://localhost:8001/v1" />
          </div>
          <div class="settings-row">
            <label for="model-default">默认模型</label>
            <select id="model-default" v-model="form.default" class="select">
              <option :value="true">是</option>
              <option :value="false">否</option>
            </select>
          </div>
        </div>
        <div class="toolbar justify-end modal-actions">
          <button class="button secondary" @click="emit('close')">取消</button>
          <button class="button" :disabled="saving" @click="submit">
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  align-items: center;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  inset: 0;
  justify-content: center;
  position: fixed;
  z-index: 1000;
}
.modal-panel {
  background: var(--panel);
  border-radius: 8px;
  box-shadow: var(--shadow);
  max-width: 560px;
  min-width: min(420px, calc(100vw - 32px));
  padding: 24px;
}
.modal-panel h2 {
  margin: 0;
}
.modal-form {
  margin-top: 16px;
}
.modal-actions {
  margin-top: 16px;
}
</style>
