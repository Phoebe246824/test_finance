<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getHealth, getHardware } from '../api/system'

const health = ref<Record<string, any>>({})
const hardware = ref<Record<string, any>>({})

async function load() {
  health.value = await getHealth()
  hardware.value = await getHardware()
}

onMounted(load)
</script>

<template>
  <section class="page-header">
    <div>
      <h1>系统状态</h1>
      <p>查看数据库、Redis 和设备信息。</p>
    </div>
  </section>

  <div class="grid-2">
    <div class="panel stack">
      <h2>健康检查</h2>
      <div class="metric" v-for="(value, key) in health" :key="key">
        <span>{{ key }}</span>
        <strong>{{ String(value) }}</strong>
      </div>
    </div>
    <div class="panel stack">
      <h2>硬件信息</h2>
      <div class="metric" v-for="(value, key) in hardware" :key="key">
        <span>{{ key }}</span>
        <strong>{{ Array.isArray(value) ? value.join(', ') : String(value) }}</strong>
      </div>
    </div>
  </div>
</template>
