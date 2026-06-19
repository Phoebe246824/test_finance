import inspect

import main


def _function_source(name: str) -> str:
    return inspect.getsource(getattr(main, name))


def test_main_imports_stage_router_helpers():
    module_source = inspect.getsource(main)

    assert 'get_llm_for' in module_source
    assert 'reasoning_kwargs_for' in module_source
    assert (
        'from providers.llm_provider import close_all_llms, get_llm'
        not in module_source
    )


def test_main_stage_llm_call_sites_use_semantic_router():
    assert 'get_llm_for("classify", 0.3)' in _function_source('classify_event')
    assert 'get_llm_for("risk_first", 0.1)' in _function_source('evaluate_risk')
    assert 'get_llm_for("risk_second", 0.1)' in _function_source(
        'second_evaluate_risk'
    )
    assert 'get_llm_for("dashboard", 0.3)' in _function_source('simulate_dashboard')
    assert 'get_llm_for("normalize", 0.3)' in _function_source(
        'normalize_payload_to_event'
    )


def test_main_reasoning_kwargs_are_attached_to_reasoning_agents_only():
    assert '**reasoning_kwargs_for("risk_first")' in _function_source('evaluate_risk')
    assert '**reasoning_kwargs_for("risk_second")' in _function_source(
        'second_evaluate_risk'
    )
    dashboard_source = _function_source('simulate_dashboard')
    assert dashboard_source.count('**reasoning_kwargs_for("dashboard")') == 2

    assert 'reasoning_kwargs_for("classify")' not in _function_source('classify_event')
    assert 'reasoning_kwargs_for("normalize")' not in _function_source(
        'normalize_payload_to_event'
    )
