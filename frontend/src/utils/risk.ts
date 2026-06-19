export function effectiveRiskLevel(item: {
  status?: string | null
  risk_level?: string | null
  risk_score?: number | null
}) {
  if (item.status === 'stashed') return 'low'
  if (item.risk_level) return item.risk_level
  if (item.risk_score === null || item.risk_score === undefined) return 'low'
  if (item.risk_score >= 0.7) return 'high'
  if (item.risk_score >= 0.35) return 'medium'
  return 'low'
}

export function riskScoreText(score?: number | null) {
  if (score === null || score === undefined) return '低风险'
  return Number(score).toFixed(4)
}

export function riskRuleText() {
  return '高风险：risk_score >= 0.70；中风险：0.35 <= risk_score < 0.70；低风险：risk_score < 0.35；未命中高危规则而暂存的事件按低风险展示。'
}
