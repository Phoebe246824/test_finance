import runpy
from pathlib import Path

import dotenv

from graphiti import graphiti_workflow as workflow


def test_graphiti_llm_config_prefers_explicit_graphiti_config_over_extract_env(monkeypatch):
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', 'extract-key')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', 'http://extract-llm.test/v1')
    monkeypatch.setenv('LLM_EXTRACT_MODEL', 'extract-model')

    resolved = workflow._resolve_graphiti_llm_config(
        {
            'api_key': 'base-key-from-config',
            'base_url': 'http://base-config.test/v1',
            'model': 'base-model-from-config',
        },
        {
            'extract_api_key': 'saved-extract-key',
            'extract_base_url': 'http://saved-extract.test/v1',
            'extract_model': 'saved-extract-model',
        },
    )

    assert resolved == {
        'api_key': 'saved-extract-key',
        'base_url': 'http://saved-extract.test/v1',
        'model': 'saved-extract-model',
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


def test_non_llm_fallbacks_use_base_llm_env_when_extract_env_is_set(
    monkeypatch,
):
    monkeypatch.setattr(dotenv, 'load_dotenv', lambda *args, **kwargs: False)
    monkeypatch.setenv('LLM_API_KEY', 'base-key')
    monkeypatch.setenv('LLM_BASE_URL', 'http://base-llm.test/v1')
    monkeypatch.setenv('LLM_EXTRACT_API_KEY', 'extract-key')
    monkeypatch.setenv('LLM_EXTRACT_BASE_URL', 'http://extract-llm.test/v1')
    monkeypatch.delenv('EMBEDDER_API_KEY', raising=False)
    monkeypatch.delenv('EMBEDDER_API_BASE', raising=False)
    monkeypatch.delenv('RERANKER_API_KEY', raising=False)
    monkeypatch.delenv('RERANKER_BASE_URL', raising=False)

    module_globals = runpy.run_path(str(Path(workflow.__file__).resolve()))

    assert module_globals['LLM_API_KEY'] == 'extract-key'
    assert module_globals['LLM_BASE_URL'] == 'http://extract-llm.test/v1'
    assert module_globals['EMBEDDER_API_KEY'] == 'base-key'
    assert module_globals['EMBEDDER_API_BASE'] == 'http://base-llm.test/v1'
    assert module_globals['RERANKER_API_KEY'] == 'base-key'
    assert module_globals['RERANKER_BASE_URL'] == 'http://base-llm.test/v1'
