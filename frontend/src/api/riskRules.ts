import { http } from './http'

export type RiskRules = {
  thresholds: Record<string, number>
  dimension_weights: Record<string, number>
  disposal_templates: Record<string, string[]>
}

export async function getRiskRules() {
  const { data } = await http.get('/api/risk-rules')
  return data as { rules: RiskRules; updated_at: string }
}

export async function updateRiskRules(rules: RiskRules) {
  const { data } = await http.put('/api/risk-rules', rules)
  return data as { rules: RiskRules; updated_at: string }
}

