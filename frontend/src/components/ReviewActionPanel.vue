<script setup lang="ts">
import { ref } from 'vue'
import { createReviewAction } from '../api/events'

const props = defineProps<{ eventId: string; actions?: any[] }>()
const emit = defineEmits<{ saved: [] }>()

const comment = ref('')
const saving = ref('')

async function save(actionType: string) {
  saving.value = actionType
  try {
    await createReviewAction(props.eventId, { action_type: actionType, comment: comment.value })
    comment.value = ''
    emit('saved')
  } finally {
    saving.value = ''
  }
}
</script>

<template>
  <div class="panel stack">
    <div class="section-title">
      <h2>人工复核</h2>
      <span class="muted small">形成风控闭环</span>
    </div>
    <div class="toolbar">
      <button class="button danger" :disabled="!!saving" @click="save('suggest_freeze')">建议冻结</button>
      <button class="button" :disabled="!!saving" @click="save('reviewed')">标记已复核</button>
      <button class="button secondary" :disabled="!!saving" @click="save('false_positive')">标记误报</button>
    </div>
    <textarea v-model="comment" class="textarea" style="min-height: 96px" placeholder="填写复核意见，可选" />
    <div class="stack">
      <div v-for="action in actions || []" :key="action.id" class="metric">
        <span>{{ action.created_at }}</span>
        <strong>{{ action.action_type }}</strong>
        <p class="muted small">{{ action.comment || '无备注' }}</p>
      </div>
      <p v-if="!(actions || []).length" class="muted">暂无复核记录</p>
    </div>
  </div>
</template>
