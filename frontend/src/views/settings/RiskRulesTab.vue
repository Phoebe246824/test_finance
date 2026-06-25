<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getRiskRules, updateRiskRules, type RiskRules } from '../../api/riskRules'
import { errorMessage } from './helpers'

const emit = defineEmits<{
  notice: [message: string]
  error: [message: string]
}>()

const saving = ref(false)
const updatedAt = ref('')
const rules = ref<RiskRules>({
  thresholds: { high: 0.7, medium: 0.35 },
  dimension_weights: {},
  disposal_templates: { high: [], medium: [], low: [] },
})

const dimensionRows = computed(() => {
  const labels: Record<string, { name: string; desc: string }> = {
    transaction_behavior: { name: '交易行为风险', desc: '基于交易金额、频次、时间等异常行为' },
    customer_identity: { name: '客户信息风险', desc: '基于客户身份、职业、历史记录等' },
    counterparty: { name: '账户关联风险', desc: '基于账户关联关系、资金流向等' },
    amount_velocity: { name: '商户风险', desc: '基于商户类型、行业风险等级' },
    device_geo: { name: '设备环境风险', desc: '设备指纹、IP、地理位置等' },
    history_context: { name: '行为画像风险', desc: '基于用户行为模式、操作习惯等' },
  }
  return Object.entries(rules.value.dimension_weights).map(([key, weight]) => ({
    key,
    name: labels[key]?.name || key,
    weight,
    desc: labels[key]?.desc || '风险维度配置',
  }))
})

const totalWeight = computed(() =>
  dimensionRows.value.reduce((sum, row) => sum + Number(row.weight || 0), 0).toFixed(2),
)

async function load(): Promise<void> {
  try {
    const data = await getRiskRules()
    rules.value = data.rules
    updatedAt.value = data.updated_at
  } catch (err: unknown) {
    emit('error', errorMessage(err, '加载规则失败'))
  }
}

async function save(): Promise<void> {
  saving.value = true
  try {
    const data = await updateRiskRules(rules.value)
    rules.value = data.rules
    updatedAt.value = data.updated_at
    emit('notice', '风险规则已保存')
  } catch (err: unknown) {
    emit('error', errorMessage(err, '保存规则失败'))
  } finally {
    saving.value = false
  }
}

function resetRule(key: string): void {
  rules.value.dimension_weights[key] = 0
}

function copyRule(row: { name: string; weight: number }): void {
  navigator.clipboard?.writeText(String(row.weight))
  emit('notice', `已复制 ${row.name} 权重值`)
}

onMounted(load)
</script>

	<template>
	  <section class="settings-section settings-split">
	    <aside class="settings-side-tabs">
	      <button class="active">评分规则</button>
	    </aside>
    <div class="settings-main-pane">
      <div class="section-title">
        <div>
          <h2>风险评分规则</h2>
          <p class="muted small">配置多维度风险评分规则及权重</p>
        </div>
      </div>
      <div class="table-wrap settings-rule-table">
        <table>
          <thead>
            <tr>
              <th>维度名称</th><th>权重</th><th>评分规则说明</th><th>状态</th><th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in dimensionRows" :key="row.key">
              <td>{{ row.name }}</td>
              <td>{{ Number(row.weight).toFixed(2) }}</td>
              <td>{{ row.desc }}</td>
              <td><span class="status-ok">启用</span></td>
              <td>
                <button class="button-link table-action" @click="copyRule(row)">复制</button>
                <button class="link-danger action-spaced" @click="resetRule(row.key)">重置</button>
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr>
              <td colspan="4">权重总和：{{ totalWeight }}　更新时间：{{ updatedAt || '未保存' }}</td>
              <td class="align-right">
                <button class="button" :disabled="saving" @click="save">
                  {{ saving ? '保存中...' : '保存权重' }}
                </button>
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  </section>
</template>
