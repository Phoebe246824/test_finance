export function effectiveRiskLevel(item: {
  status?: string | null
  risk_level?: string | null
  risk_score?: number | null
}) {
  if (item.status === 'stashed' || item.risk_score === null || item.risk_score === undefined) {
    return 'pending'
  }
  if (item.risk_level) return item.risk_level
  if (item.risk_score >= 0.7) return 'high'
  if (item.risk_score >= 0.35) return 'medium'
  return 'low'
}

export function riskScoreText(score?: number | null) {
  if (score === null || score === undefined) return '未评估'
  return Number(score).toFixed(4)
}

export function riskRuleText() {
  return '高风险：risk_score >= 0.70；中风险：0.35 <= risk_score < 0.70；低风险：risk_score < 0.35；未命中黑名单而暂存的事件显示为待评估。'
}
