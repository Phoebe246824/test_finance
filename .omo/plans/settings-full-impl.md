# settings-full-impl - Work Plan

## TL;DR (For humans)
**What you'll get:** The Web settings page will manage a complete configuration dictionary seeded from every `.env.example` item, create the first settings file from defaults plus `.env`, persist edits, and drive Web-triggered trend prediction from the saved runtime-effective subset.

**Why this approach:** It gives the Web demo one canonical editable config surface while preserving existing terminal/script behavior. Environment variables remain the source for scripts, and WebUI uses them only for first setup and blank secret fallback.

**What it will NOT do:** It will not pretend build-time/frontend/server-bind/Docker values can affect an already-running process without restart/rebuild/recreate. It will not move command-line pipelines or operational scripts onto the Web settings file. It will not replace the JSON settings file with a new database. It will not expose secrets in logs, notices, or plain UI text.

**Effort:** Large
**Risk:** High - the work crosses settings persistence, API schemas, frontend editing, and the live analysis/trend-prediction runtime boundary.
**Decisions to sanity-check:** The main product decision is the Web/CLI split: Web analysis reads saved Web settings, terminal scripts continue reading environment variables. The other notable decisions are that `.env.example` is the complete catalog source and blank saved secrets may fall back to environment variables.

Your next move: start execution when ready. Full execution detail follows below.

---

> TL;DR (machine): Large/high-risk plan for full Web runtime settings bootstrap, editor, Web analysis consumption, CLI/script env separation, and end-to-end QA.

## Scope
### Must have
- A complete WebUI settings dictionary exists under the persisted app settings payload and covers every configuration item in `.env.example`, including runtime items, Web/server items, Docker/Compose ports/credentials, auth tokens, target platform markers, and optional integration settings.
- Each config item carries typed metadata: group, key path, env variable name, label/help text, scalar type, default value, secret flag, editable flag, and effective scope. Effective scope must distinguish at least `runtime_immediate`, `web_restart`, `frontend_rebuild`, `compose_recreate`, and `display_only`.
- Every Web-triggered analysis/trend-prediction runtime item is mapped into the exact config shape expected by `process_message_detailed()`: Neo4j, LLM base/stage config, embedder, reranker, Graphiti, search, classification, risk scoring weights, Milvus stash settings, RAGFlow, and blacklist thresholds.
- When the Web settings file is missing, loading settings creates the initial persisted file from defaults overlaid by `.env`/current environment values. Existing `SENTINEL_SETTINGS_FILE` behavior remains supported.
- After a Web settings file exists, user-saved values are stable and are not silently overwritten by environment changes, except API key/secret fallback behavior described below.
- WebUI may read environment variables only for two purposes: first-bootstrap overlay and runtime API key/secret fallback when the persisted Web setting leaves the secret blank.
- Terminal pipeline/scripts remain environment-driven. `main.load_config()` and operational scripts must keep their current env behavior unless the caller explicitly passes a config.
- Web API analysis path uses a WebUI-specific config loading path, then passes that config into `process_message_detailed()` so trend prediction receives the Web settings dictionary.
- Frontend settings page shows all config dictionary groups and values from backend metadata, supports editing scalar/list/bool/secret values, displays each field's effective-scope note, and persists changes to the settings JSON file.
- Existing specialized settings tabs (`系统设置`, `模型设置`, `规则配置`, `操作日志`, `数据管理`, `通知设置`) continue working.
- Model service overrides continue to work for Web analysis runtime and must not be broken by the full config editor.
- New tests prove first-bootstrap env overlay, persistence, Web-vs-CLI separation, settings API validation, frontend type/build correctness, and Web-triggered trend prediction config consumption.

### Must NOT have (guardrails, anti-slop, scope boundaries)
- Do not migrate CLI pipeline, scripts, or demo utilities to read Web settings by default.
- Do not silently apply `frontend_rebuild`, `web_restart`, or `compose_recreate` fields to a running process. Persist and display them, but show the required action.
- Do not replace the existing JSON persistence with a database, Redis, or another storage dependency.
- Do not remove or weaken existing settings validation/audit behavior.
- Do not persist generated temp artifacts, screenshots, or QA evidence outside `.omo/evidence/`.
- Do not expose secrets in notices, audit details, log lines, visible table summaries, or final reports. Secret fields may be edited but must render as password/masked controls in the frontend.
- Do not change the public contract of existing specialized endpoints unless backwards compatibility is preserved.
- Do not use `gpt-5.4-mini` subagents; that model is unavailable in this environment. If subagents are required during execution, use `gpt-5.4` or main-thread work.

### Required config catalog coverage
The executor must treat `.env.example` as the authoritative catalog input and explicitly cover the following fields. Do not omit a field because it is not currently consumed by trend prediction; instead set its `effective_scope` correctly.

| Group | Fields |
| --- | --- |
| Web service | `BACKEND_HOST`, `BACKEND_PORT`, `VITE_API_BASE_URL` |
| Neo4j / Graphiti | `NEO4J_HTTP_PORT`, `NEO4J_BOLT_PORT`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `NEO4J_DATABASE`, `GRAPHITI_DRY_RUN`, `GRAPHITI_EPISODE_SOURCE` |
| Target platform | `SENTINEL_TARGET_PLATFORM`, `SENTINEL_GPU_BACKEND`, `SENTINEL_NPU_BACKEND`, `RYZEN_AI_HOME` |
| LLM base | `LLM_PROVIDER`, `LLM_MODEL`, `LLM_API_KEY`, `LLM_BASE_URL` |
| LLM extract tier | `LLM_EXTRACT_BASE_URL`, `LLM_EXTRACT_MODEL`, `LLM_EXTRACT_API_KEY` |
| LLM reason tier | `LLM_REASON_BASE_URL`, `LLM_REASON_MODEL`, `LLM_REASON_API_KEY`, `REASON_MAX_ATTEMPTS`, `REASON_MAX_STEPS` |
| Embedder | `EMBEDDER_MODEL`, `EMBEDDER_API_KEY`, `EMBEDDER_API_BASE`, `EMBEDDING_DIM` |
| Reranker | `RERANKER_MODEL`, `RERANKER_API_KEY`, `RERANKER_BASE_URL` |
| RAGFlow runtime | `RAGFLOW_ENABLED`, `RAGFLOW_BASE_URL`, `RAGFLOW_API_KEY`, `RAGFLOW_DATASET_ID`, `RAGFLOW_DATASET_IDS`, `RAGFLOW_TOP_K`, `RAGFLOW_SIMILARITY_THRESHOLD`, `RAGFLOW_VECTOR_SIMILARITY_WEIGHT`, `RAGFLOW_TIMEOUT_SECONDS`, `RAGFLOW_MAX_CONTEXT_CHARS`, `RAGFLOW_FAIL_OPEN` |
| RAGFlow deployment | `RAGFLOW_IMAGE`, `RAGFLOW_WEB_PORT`, `RAGFLOW_API_PORT`, `RAGFLOW_MYSQL_PASSWORD`, `RAGFLOW_REDIS_PASSWORD`, `RAGFLOW_MINIO_USER`, `RAGFLOW_MINIO_PASSWORD`, `RAGFLOW_ELASTIC_PASSWORD` |
| Search / risk | `SEARCH_NUM_RESULTS`, `RISK_SEARCH_NUM_RESULTS`, `SEARCH_MIN_SCORE`, `RISK_THRESHOLD`, `RISK_WEIGHT_CUSTOMER_IDENTITY`, `RISK_WEIGHT_TRANSACTION_BEHAVIOR`, `RISK_WEIGHT_COUNTERPARTY`, `RISK_WEIGHT_AMOUNT_VELOCITY`, `RISK_WEIGHT_DEVICE_GEO`, `RISK_WEIGHT_HISTORY_CONTEXT`, `RISK_WEIGHT_COMPLIANCE_SIGNAL` |
| Milvus / MinIO / Attu | `MINIO_API_PORT`, `MINIO_CONSOLE_PORT`, `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY`, `MILVUS_GRPC_PORT`, `MILVUS_HTTP_PORT`, `ATTU_PORT`, `MILVUS_URI`, `MILVUS_TOKEN`, `MILVUS_STASH_COLLECTION`, `STASH_SEMANTIC_TOP_K`, `STASH_RERANK_ENABLED`, `STASH_RERANK_MIN_SCORE`, `BATCH_MAX_PER_PERSON`, `KV_TTL_DAYS` |
| Blacklist | `BLACKLIST_EVENT_SIMILARITY_THRESHOLD`, `BLACKLIST_PERSON_MIN_HITS` |
| Auth | `AUTH_ENABLED`, `SENTINEL_ADMIN_TOKEN`, `SENTINEL_REVIEWER_TOKEN` |

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: tests-after, because this is an integration of existing settings/pipeline surfaces rather than a greenfield algorithm. Each implementation todo includes tests before the todo is considered complete.
- Backend unit/API tests: `uv run pytest tests/settings_demo/test_settings_core.py tests/settings_demo/test_model_services.py tests/test_main_llm_stage_wiring.py -q`.
- Add focused tests under `tests/settings_demo/` for Web settings bootstrap, Web runtime config generation, Web-vs-CLI separation, and API validation.
- Frontend checks: from `frontend/`, run `npm run test` and `npm run build`.
- LSP/diagnostics: run diagnostics on changed Python and TypeScript/Vue files where LSP is available.
- Manual QA gate: start backend/frontend if feasible, drive the Settings page in browser, save a runtime config value, reload, and run a Web API analysis with fakes/mocks or a controlled request proving trend prediction receives Web settings. If live services are unavailable, run the equivalent FastAPI/TestClient scenario and record why browser/live analysis was substituted.
- Evidence paths:
  - `.omo/evidence/task-1-settings-full-impl.md`
  - `.omo/evidence/task-2-settings-full-impl.md`
  - `.omo/evidence/task-3-settings-full-impl.md`
  - `.omo/evidence/task-4-settings-full-impl.md`
  - `.omo/evidence/task-5-settings-full-impl.md`
  - `.omo/evidence/task-6-settings-full-impl.md`
  - `.omo/evidence/task-7-settings-full-impl.md`
  - `.omo/evidence/final-settings-full-impl.md`

## Execution strategy
### Parallel execution waves
> Target 5-8 todos per wave. Fewer than 3 (except the final) means you under-split.
- Wave 1, backend foundation: Todos 1-3. These establish Web runtime config schema/bootstrap, persistence/API payloads, and explicit Web-vs-CLI config loaders. Todo 1 blocks most others.
- Wave 2, runtime integration and frontend: Todos 4-6. Todo 4 depends on Web config loader; Todo 5 depends on API/types; Todo 6 can run once the frontend editor exists.
- Wave 3, end-to-end verification and documentation polish: Todo 7 plus final verification wave.

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
| --- | --- | --- | --- |
| 1. Web runtime config schema/bootstrap | none | 2, 3, 4, 5 | none |
| 2. Settings persistence/API schemas | 1 | 5, 7 | 3 |
| 3. Web-vs-CLI config loading boundary | 1 | 4, 7 | 2 |
| 4. Web analysis/trend prediction consumes Web config | 3 | 7 | 5 after shared type shape is stable |
| 5. Frontend complete config editor | 1, 2 | 6, 7 | 4 |
| 6. Frontend styling/state QA hardening | 5 | 7 | backend tests in 4 |
| 7. End-to-end regression and manual QA evidence | 2, 4, 6 | final verification | none |

## Todos
> Implementation + Test = ONE todo. Never separate.
<!-- APPEND TASK BATCHES BELOW THIS LINE WITH edit/apply_patch - never rewrite the headers above. -->
- [ ] 1. Add complete config catalog defaults, env overlay, and first-bootstrap persistence
  What to do / Must NOT do: Create a backend service module, recommended path `backend/app/services/settings_runtime_config.py`, that owns the complete Web settings config dictionary and metadata. It must define defaults for every config key in `.env.example`, including runtime, Web/server, frontend-build, Docker/Compose, auth, and platform-marker fields. It must provide functions equivalent to: build defaults, load `.env` into process before first bootstrap overlay, overlay supported env vars with type coercion, convert stored Web settings into the runtime config shape expected by `process_message_detailed()`, list field metadata for the frontend, and expose an effective-scope marker for fields that require restart/rebuild/recreate. It must not alter CLI/script env loading.
  Parallelization: Wave 1 | Blocked by: none | Blocks: 2, 3, 4, 5
  References (executor has NO interview context - be exhaustive): `backend/app/services/settings_defaults.py:13`; `backend/app/services/settings_service.py:47`; `backend/app/services/settings_storage.py:21`; `main.py:106`; `main.py:113`; `.env.example`; `docs/env-vars.md`; `providers/llm_provider.py`; `providers/embedder_provider.py`; `graphiti/graphiti_workflow.py`; `trend_prediction/classifier.py:499`.
  Acceptance criteria (agent-executable): Add pytest coverage proving missing settings file initializes a persisted JSON file whose `settings.runtime_config` includes every `.env.example` field, values from env override defaults on first bootstrap, numeric/bool/list coercion works, required effective-scope metadata is present, and a later env change does not overwrite an existing saved value.
  QA scenarios (name the exact tool + invocation): Happy: `SENTINEL_SETTINGS_FILE=$(mktemp -u) LLM_MODEL=env-web-model RAGFLOW_ENABLED=true uv run pytest tests/settings_demo/test_settings_core.py -q -k 'bootstrap or runtime_config'`, evidence `.omo/evidence/task-1-settings-full-impl.md`. Failure: corrupt JSON at `SENTINEL_SETTINGS_FILE` falls back through the same bootstrap path and records a warning without crashing, evidence in the same file.
  Commit: Y | `feat(settings): bootstrap complete web runtime config`

- [ ] 2. Extend settings persistence and API schemas without breaking existing section endpoints
  What to do / Must NOT do: Extend `DEFAULT_SETTINGS`, `load_app_settings()`, `save_app_settings()`, `AppSettingsPayload`, and frontend-facing response shape to include `runtime_config` and config metadata. Preserve existing `system-config`, `model-params`, `data-management`, `notification-events`, model-service, and notification endpoints. Reject unsupported config keys and invalid scalar/list/bool/secret types with 422/400. Keep audit logs, `extra="forbid"` behavior for known payloads, and model service validation.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 5, 7
  References: `backend/app/api/routes_settings.py:15`; `backend/app/api/routes_settings.py:85`; `backend/app/api/routes_settings.py:97`; `backend/app/api/routes_settings.py:129`; `backend/app/services/settings_service.py:16`; `backend/app/services/settings_service.py:52`; `backend/app/services/model_runtime_config.py:28`; `tests/settings_demo/test_settings_core.py`; `tests/settings_demo/test_model_services.py`.
  Acceptance criteria (agent-executable): Existing settings tests still pass. New tests prove `GET /api/settings` returns `runtime_config` plus metadata, `PUT /api/settings` persists it, section updates do not overwrite newer `runtime_config`, every `.env.example` variable has a returned metadata entry, and extra unknown config groups/fields are rejected unless explicitly marked supported.
  QA scenarios: Happy: `uv run pytest tests/settings_demo/test_settings_core.py tests/settings_demo/test_model_services.py -q`, evidence `.omo/evidence/task-2-settings-full-impl.md`. Failure: send `{"runtime_config":{"unknown_group":{"x":1}}}` through TestClient and assert 422/400 without file corruption.
  Commit: Y | `feat(settings): expose full runtime config in api`

- [ ] 3. Add explicit WebUI runtime config loader while preserving CLI/script env behavior
  What to do / Must NOT do: Add a Web-specific loader, recommended function `load_web_runtime_config()` in the new settings runtime service or a clearly named adjacent module. It must map only runtime-effective catalog fields into the nested dictionary expected by `process_message_detailed()`. Update Web API service code to use it. Keep `main.load_config()` env-driven for CLI/terminal pipeline and scripts. If a Web caller needs runtime config, it must call the Web loader and pass the result into `process_message_detailed()`. Ensure API key/secret fallback reads environment only when the stored Web setting is empty.
  Parallelization: Wave 1 | Blocked by: 1 | Blocks: 4, 7
  References: `main.py:106`; `main.py:1976`; `backend/app/services/analysis_service.py:3`; `backend/app/services/analysis_service.py:28`; `backend/app/services/store_provider.py`; `backend/app/services/neo4j_graph_service.py`; `scripts/reset_and_seed_blacklist.py`; `scripts/run_blacklist_kv_demo.py`; `scripts/cleanup_milvus_duplicates.py`.
  Acceptance criteria (agent-executable): Tests prove `main.load_config()` still reflects changed env vars even when Web settings file exists, while `load_web_runtime_config()` returns persisted Web settings and only falls back to env for blank secret fields. Tests prove `AnalysisService.analyze()` passes the Web config into `process_message_detailed()` for both progress and non-progress paths.
  QA scenarios: Happy: `uv run pytest tests/settings_demo/test_settings_core.py -q -k 'web_runtime or cli_env'`, evidence `.omo/evidence/task-3-settings-full-impl.md`. Failure: save Web `llm.model = saved-model`, then monkeypatch `LLM_MODEL=env-model`; assert Web loader returns `saved-model` and `main.load_config()` returns `env-model`.
  Commit: Y | `feat(settings): separate web and cli config sources`

- [ ] 4. Route Web analysis and trend prediction through the persisted Web runtime config
  What to do / Must NOT do: Update `backend/app/services/analysis_service.py` and the Web analysis path so all Web-triggered event analysis uses the Web loader, applies risk rules, and passes config into `process_message_detailed()`. Where provider helpers are used during Web-triggered trend prediction (`get_llm_for`, `EventClassifier`, reranker, RAGFlow, Graphiti), ensure config values are either passed through existing function params or read from the Web runtime config context. Avoid global env mutation as the main mechanism; if a transitional context variable is necessary, scope it to the request and test isolation. Do not migrate standalone scripts. Non-runtime catalog fields must not be consulted during the prediction pipeline.
  Parallelization: Wave 2 | Blocked by: 3 | Blocks: 7
  References: `backend/app/services/analysis_service.py:11`; `main.py:1108`; `main.py:1153`; `main.py:1201`; `main.py:1344`; `trend_prediction/classifier.py:499`; `providers/llm_provider.py:105`; `providers/llm_provider.py:132`; `graphiti/graphiti_workflow.py:57`; `graphiti/graphiti_workflow.py:194`; `tests/test_main_llm_stage_wiring.py`.
  Acceptance criteria (agent-executable): Add tests with fakes/mocks proving Web analysis reaches `simulate_dashboard()`/trend prediction with config derived from persisted Web settings, and reranker/RAGFlow/model config values resolve from Web settings rather than env except for blank secrets. Existing `tests/test_main_llm_stage_wiring.py` keeps passing.
  QA scenarios: Happy: `uv run pytest tests/test_main_llm_stage_wiring.py tests/settings_demo/test_settings_core.py -q -k 'trend or web_runtime or stage'`, evidence `.omo/evidence/task-4-settings-full-impl.md`. Failure: Web settings set RAGFlow fail-closed/timeout values and env differs; mocked `retrieve_financial_knowledge` observes the Web settings values.
  Commit: Y | `feat(analysis): use web settings for web trend prediction`

- [ ] 5. Build the frontend complete configuration editor
  What to do / Must NOT do: Extend `frontend/src/api/settings.ts` with strict types for `runtime_config` and metadata. Add a Settings tab (recommended label `完整配置`) and a component such as `frontend/src/views/settings/RuntimeConfigTab.vue`. Render all groups and fields from backend metadata or a stable typed response. Use appropriate controls: checkbox/toggle for booleans, number inputs for numbers, text/password input for strings/secrets, comma/newline list editor for string lists. Show effective-scope notes for fields requiring restart/rebuild/recreate. Preserve specialized tabs and store behavior. Do not show secrets in clear text by default; do not introduce unrelated UI libraries.
  Parallelization: Wave 2 | Blocked by: 1, 2 | Blocks: 6, 7
  References: `frontend/src/api/settings.ts:49`; `frontend/src/views/SettingsView.vue:10`; `frontend/src/views/settings/SystemSettingsTab.vue`; `frontend/src/views/settings/ModelSettingsTab.vue`; `frontend/src/views/settings/helpers.ts`; `frontend/src/stores/appSettings.ts`; `DESIGN.md`; `frontend/package.json`.
  Acceptance criteria (agent-executable): Frontend build passes. A node/Vue-adjacent helper test or TypeScript-safe unit script covers value serialization/deserialization for booleans, numbers, strings, secrets, and lists, plus scope-note rendering data. Existing `npm run test` still passes.
  QA scenarios: Happy: `cd frontend && npm run test && npm run build`, evidence `.omo/evidence/task-5-settings-full-impl.md`. Failure: attempt to save invalid number/list value in the UI helper path and assert the save call is blocked or API error is surfaced with `emit('error')` pattern.
  Commit: Y | `feat(frontend): add complete runtime config editor`

- [ ] 6. Harden settings editor UX, styling, and browser behavior
  What to do / Must NOT do: Integrate the new tab with existing `DESIGN.md` tokens and `frontend/src/styles.css` patterns. Ensure dense operational layout, no nested cards, stable field widths, no horizontal overflow, visible loading/saving/error states, filter/search by group or env name, and keyboard-accessible controls. Secret fields must have reveal/edit affordance without leaking values in page text. Scope notes should be compact, not explanatory marketing copy. Keep the page visually consistent with existing Settings tabs.
  Parallelization: Wave 2 | Blocked by: 5 | Blocks: 7
  References: `DESIGN.md`; `frontend/src/styles.css`; `frontend/src/views/SettingsView.vue`; `frontend/src/views/settings/*.vue`; `frontend/package.json`; frontend skill requirements already loaded in planning.
  Acceptance criteria (agent-executable): Browser or screenshot QA at mobile/tablet/desktop shows the new tab renders all groups without overlap or horizontal scroll. Build/test commands pass after styling changes.
  QA scenarios: Happy: start Vite preview/dev server, open `/settings`, switch to `完整配置`, capture screenshots at 375, 768, and 1280 px, evidence `.omo/evidence/task-6-settings-full-impl.md`. Failure: force API error or invalid payload and verify error banner appears without layout shift; evidence in the same file.
  Commit: Y | `style(settings): polish complete config editor`

- [ ] 7. Run end-to-end regression and record final evidence
  What to do / Must NOT do: Execute the whole feature through its matching surfaces. Use a temp `SENTINEL_SETTINGS_FILE`; set env vars spanning at least one field from each major config group; trigger `GET /api/settings` to bootstrap; verify file exists and contains defaults overlaid by env; update a runtime config field and a non-runtime config field through API and frontend if server/browser is available; reload and verify persistence; run Web API analysis/trend path with fakes/mocks or controlled services; separately prove CLI/script env behavior remains unchanged. Do not claim live Neo4j/Milvus/LLM success if those services are unavailable; record substituted mocks clearly.
  Parallelization: Wave 3 | Blocked by: 2, 4, 6 | Blocks: final verification
  References: all changed files; `docs/commands.md`; `docs/testing.md`; `tests/settings_demo/conftest.py`; `backend/app/main.py`; `frontend/package.json`.
  Acceptance criteria (agent-executable): All targeted backend tests pass, frontend tests/build pass, manual QA evidence file contains command outputs/summaries and screenshots or explicit reason for API-level substitute, and no changed-file LSP diagnostics remain.
  QA scenarios: Happy: run full command set from verification strategy and record outputs to `.omo/evidence/task-7-settings-full-impl.md`. Failure: intentionally change env after Web settings save and assert Web path remains persisted while CLI path changes with env.
  Commit: Y | `test(settings): verify full web config flow`

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE. Surface results and wait for the user's explicit okay before declaring complete.
- [ ] F1. Plan compliance audit
  Verify every Must Have and Must NOT Have is covered by code/tests/evidence. Reject if WebUI and CLI config sources are not explicitly separated.
- [ ] F2. Code quality review
  Review changed Python/TypeScript/Vue for typed boundaries, schema drift, secret leakage, overbroad env access, and oversized modules. Reject on `Any`/`any` expansion in public surfaces or hidden type suppressions.
- [ ] F3. Real manual QA
  Drive the Settings page and Web analysis surface, or document controlled substitute if external services are unavailable. Must include first-bootstrap, edit/save/reload, and Web trend config consumption.
- [ ] F4. Scope fidelity
  Confirm no terminal scripts, demo scripts, or CLI `main.load_config()` were migrated to Web settings by default. Confirm no unrelated refactors or dependency swaps landed.

## Commit strategy
- Preferred commits are per todo, in dependency order:
  1. `feat(settings): bootstrap complete web runtime config`
  2. `feat(settings): expose full runtime config in api`
  3. `feat(settings): separate web and cli config sources`
  4. `feat(analysis): use web settings for web trend prediction`
  5. `feat(frontend): add complete runtime config editor`
  6. `style(settings): polish complete config editor`
  7. `test(settings): verify full web config flow`
- If the user does not ask for commits during execution, leave changes unstaged and report the suggested commit split.
- Never amend existing commits unless explicitly requested.

## Success criteria
- A missing Web settings file is automatically created from full defaults overlaid by `.env`/environment values.
- The persisted settings file contains the complete Web runtime config dictionary and existing UI settings sections.
- Frontend Settings shows and edits every Web runtime config item, persists saves, and reloads saved values.
- Web API-triggered event analysis/trend prediction reads from persisted Web settings, with environment fallback only for blank API key/secret values.
- Terminal pipeline/scripts continue to read configuration from environment variables by default.
- Existing settings/model service behavior continues to pass tests.
- Backend tests, frontend tests/build, changed-file diagnostics, and manual QA evidence all pass or document only external-service limitations.
