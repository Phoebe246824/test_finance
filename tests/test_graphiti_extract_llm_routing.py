from graphiti import graphiti_workflow as workflow


def test_graphiti_llm_config_prefers_extract_env_over_base_config(monkeypatch):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', 'extract-key')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', 'http://extract-llm.test/v1')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', 'extract-model')

    resolved = workflow._resolve_graphiti_llm_config(
        {
            'api_key': 'base-key-from-config',
            'base_url': 'http://base-config.test/v1',
            'model': 'base-model-from-config',
        }
    )

    assert resolved == {
        'api_key': 'extract-key',
        'base_url': 'http://extract-llm.test/v1',
        'model': 'extract-model',
    }


def test_graphiti_llm_config_falls_back_to_base_config_when_extract_env_is_blank(
    monkeypatch,
):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', '')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', '')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', '')

    resolved = workflow._resolve_graphiti_llm_config(
        {
            'api_key': 'base-key-from-config',
            'base_url': 'http://base-config.test/v1',
            'model': 'base-model-from-config',
        }
    )

    assert resolved == {
        'api_key': 'base-key-from-config',
        'base_url': 'http://base-config.test/v1',
        'model': 'base-model-from-config',
    }


def test_graphiti_llm_config_uses_module_defaults_without_config(monkeypatch):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', '')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', '')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', '')

    resolved = workflow._resolve_graphiti_llm_config()

    assert resolved['api_key'] == workflow.LLM_API_KEY
    assert resolved['base_url'] == workflow.LLM_BASE_URL
    assert resolved['model'] == workflow.LLM_MODEL
