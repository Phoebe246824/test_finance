from main import build_weighted_risk_result


def test_model_reported_risk_score_is_preserved_for_downstream_steps():
    config = {
        "risk_scoring": {
            "dimensions": {
                "customer_identity": 0.15,
                "transaction_behavior": 0.25,
                "counterparty": 0.20,
                "amount_velocity": 0.15,
                "device_geo": 0.10,
                "history_context": 0.10,
                "compliance_signal": 0.05,
            }
        }
    }
    result = build_weighted_risk_result(
        {
            "dimension_scores": {
                "customer_identity": 0.3,
                "transaction_behavior": 0.9,
                "counterparty": 1.0,
                "amount_velocity": 0.8,
                "device_geo": 0.9,
                "history_context": 0.7,
                "compliance_signal": 1.0,
            },
            "risk_score": 0.795,
            "risk_level": "high",
        },
        config,
    )

    assert result["risk_score"] == 0.795
    assert result["risk_level"] == "high"
    assert result["risk_score_source"] == "model_reported"
    assert result["calculated_risk_score"] == 0.8
