import importlib

import pytest


BASE_ENV = {
    'LLM_MODEL': 'base-model',
    'LLM_API_KEY': 'base-key',
    'LLM_BASE_URL': 'http://base-llm.test/v1',
}

STAGE_ENV_KEYS = [
    'LLM_EXTRACT_MODEL',
    'LLM_EXTRACT_API_KEY',
    'LLM_EXTRACT_BASE_URL',
    'LLM_REASON_MODEL',
    'LLM_REASON_API_KEY',
    'LLM_REASON_BASE_URL',
    'REASON_MAX_ATTEMPTS',
    'REASON_MAX_STEPS',
]


def reload_provider(monkeypatch, env: dict[str, str]):
    for key in STAGE_ENV_KEYS:
        monkeypatch.setenv(key, '')
    for key, value in BASE_ENV.items():
        monkeypatch.setenv(key, value)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    import providers.llm_provider as llm_provider

    return importlib.reload(llm_provider)


def test_get_llm_for_uses_base_llm_when_tier_env_is_blank(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': '2'})

    extract_llm = llm_provider.get_llm_for('normalize', 0.3)
    reason_llm = llm_provider.get_llm_for('risk_first', 0.1)

    assert extract_llm.model == 'base-model'
    assert extract_llm.api_key == 'base-key'
    assert extract_llm.base_url == 'http://base-llm.test/v1'
    assert extract_llm.temperature == 0.3

    assert reason_llm.model == 'base-model'
    assert reason_llm.api_key == 'base-key'
    assert reason_llm.base_url == 'http://base-llm.test/v1'
    assert reason_llm.temperature == 0.1
    assert extract_llm in llm_provider._ACTIVE_LLMS
    assert reason_llm in llm_provider._ACTIVE_LLMS


def test_get_llm_for_prefers_tier_specific_endpoint(monkeypatch):
    llm_provider = reload_provider(
        monkeypatch,
        {
            'LLM_EXTRACT_MODEL': 'extract-model',
            'LLM_EXTRACT_API_KEY': 'extract-key',
            'LLM_EXTRACT_BASE_URL': 'http://extract-llm.test/v1',
            'LLM_REASON_MODEL': 'reason-model',
            'LLM_REASON_API_KEY': 'reason-key',
            'LLM_REASON_BASE_URL': 'http://reason-llm.test/v1',
            'REASON_MAX_ATTEMPTS': '2',
        },
    )

    classify_llm = llm_provider.get_llm_for('classify', 0.3)
    risk_llm = llm_provider.get_llm_for('risk_second', 0.1)

    assert classify_llm.model == 'extract-model'
    assert classify_llm.api_key == 'extract-key'
    assert classify_llm.base_url == 'http://extract-llm.test/v1'

    assert risk_llm.model == 'reason-model'
    assert risk_llm.api_key == 'reason-key'
    assert risk_llm.base_url == 'http://reason-llm.test/v1'


def test_get_llm_for_warns_when_falling_back_to_default_cloud_base_url(
    monkeypatch, caplog
):
    llm_provider = reload_provider(
        monkeypatch,
        {
            'LLM_BASE_URL': '',
            'LLM_EXTRACT_BASE_URL': '',
            'REASON_MAX_ATTEMPTS': '2',
        },
    )

    llm = llm_provider.get_llm_for('normalize', 0.3)

    assert llm.base_url == 'https://api.openai.com/v1'
    assert 'default cloud LLM base_url' in caplog.text
    assert 'local demo constraint' in caplog.text


def test_get_llm_for_rejects_unknown_stage(monkeypatch):
    llm_provider = reload_provider(monkeypatch, {'REASON_MAX_ATTEMPTS': '2'})

    with pytest.raises(ValueError, match='unknown LLM stage'):
        llm_provider.get_llm_for('unknown_stage', 0.3)


def test_reasoning_kwargs_are_enabled_only_for_reason_tier(monkeypatch):
    llm_provider = reload_provider(
        monkeypatch,
        {'REASON_MAX_ATTEMPTS': '4', 'REASON_MAX_STEPS': '3'},
    )

    first_config = llm_provider.reasoning_kwargs_for('risk_first')['planning_config']
    second_config = llm_provider.reasoning_kwargs_for('risk_second')['planning_config']
    assert first_config.max_attempts == 4
    assert first_config.max_steps == 3
    assert second_config.max_attempts == 4
    assert second_config.max_steps == 3
    assert llm_provider.reasoning_kwargs_for('dashboard') == {}
    assert llm_provider.reasoning_kwargs_for('normalize') == {}
    assert llm_provider.reasoning_kwargs_for('classify') == {}
    assert llm_provider.reasoning_kwargs_for('graphiti') == {}


def test_reasoning_kwargs_default_to_two_attempts_and_four_steps(monkeypatch):
    llm_provider = reload_provider(
        monkeypatch,
        {'REASON_MAX_ATTEMPTS': '', 'REASON_MAX_STEPS': ''},
    )

    planning_config = llm_provider.reasoning_kwargs_for('risk_first')['planning_config']
    assert planning_config.max_attempts == 2
    assert planning_config.max_steps == 4
