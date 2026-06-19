<script setup lang="ts">
defineProps<{ blacklist?: Record<string, any> | null }>()
</script>

<template>
  <div class="panel stack">
    <h2>黑名单命中</h2>
    <div class="metric">
      <span>决策</span>
      <strong>{{ blacklist?.decision || '未知' }}</strong>
    </div>

    <div>
      <p class="muted small">人员命中</p>
      <div class="hit-list">
        <span v-for="person in blacklist?.matched_persons || []" :key="person" class="chip">
          {{ person }}
        </span>
        <span v-if="!(blacklist?.matched_persons || []).length" class="muted small">无</span>
      </div>
    </div>

    <div>
      <p class="muted small">关键词命中</p>
      <div class="hit-list">
        <span v-for="keyword in blacklist?.matched_keywords || []" :key="keyword" class="chip">
          {{ keyword }}
        </span>
        <span v-if="!(blacklist?.matched_keywords || []).length" class="muted small">无</span>
      </div>
    </div>

    <div>
      <p class="muted small">相似事件</p>
      <p class="pre-wrap small">
        {{
          blacklist?.event_similarity?.hit
            ? `${blacklist.event_similarity.event_id || '未知事件'} / ${blacklist.event_similarity.summary || '无摘要'}`
            : '未命中'
        }}
      </p>
    </div>
  </div>
</template>
