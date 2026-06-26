---
slug: settings-full-impl
status: plan-written
intent: clear
pending-action: write .omo/plans/settings-full-impl.md
approach: Build one backend-owned settings catalog from defaults + .env metadata, persist it on first Web settings load, expose it through the existing settings API, render it dynamically in the Vue settings page, and make Web-triggered analysis/trend prediction consume the persisted runtime subset.
---

# Draft: settings-full-impl

## Components (topology ledger)
<!-- Lock the SHAPE before depth. One row per top-level component that can succeed or fail independently. -->
<!-- id | outcome (one line) | status: active|deferred | evidence path -->
| C1 | Full settings catalog/defaults/env overlay creates a first settings file when missing | active | backend/app/services/settings_defaults.py; backend/app/services/settings_storage.py; main.py |
| C2 | Settings API persists and validates the full config dictionary without breaking existing section endpoints | active | backend/app/api/routes_settings.py; backend/app/services/settings_service.py |
| C3 | Web analysis and trend prediction read the persisted Web runtime config on every Web-triggered run | active | backend/app/services/analysis_service.py; main.py |
| C4 | Frontend settings page displays every config item from backend metadata and saves edits | active | frontend/src/views/SettingsView.vue; frontend/src/api/settings.ts; DESIGN.md |
| C5 | Regression/manual QA proves bootstrap, persistence, UI editing, Web trend config consumption, and CLI/env compatibility | active | tests/settings_demo; tests/test_main_llm_stage_wiring.py; docs/testing.md |

## Open assumptions (announced defaults)
<!-- Record any default you adopt instead of asking, so the user can veto it at the gate. -->
<!-- assumption | adopted default | rationale | reversible? -->
| Full config scope | Treat `.env.example` as the authoritative config catalog; every variable there gets a default, label, type, group, env name, and effective scope. | It is the repository's current complete env surface and is mirrored by docs/env-vars.md. | yes |
| Runtime vs deployment effect | Persist every config item, but only analysis/runtime items affect already-running Web analysis immediately; frontend build-time, server bind-port, and Docker Compose values are stored/displayed and marked "restart/rebuild/recompose required". | Some settings cannot affect an already-built Vite bundle or already-started server/container without restart. | yes |
| Web/CLI boundary | Web-triggered analysis uses the persisted Web settings file; CLI/scripts keep env-driven behavior unless they explicitly pass a config dictionary. | The current project keeps Web demo and terminal pipeline as related but distinct entrypoints. | yes |
| Secrets | Blank persisted secret fields may fall back to environment variables at runtime; non-blank secrets are masked in UI and never logged. | This preserves `.env` safety while letting Web settings override local defaults. | yes |

## Findings (cited - path:lines)
- `backend/app/services/settings_defaults.py:13` currently defines only demo UI settings, not the complete runtime/env config surface.
- `backend/app/services/settings_storage.py:21` already supports `SENTINEL_SETTINGS_FILE` and JSON persistence at `data/app_settings.json`.
- `backend/app/services/runtime_state.py:68` loads settings from file but does not persist defaults when the file is missing.
- `backend/app/services/settings_service.py:47` merges stored settings over `DEFAULT_SETTINGS`, so a richer defaults/catalog layer can be added without replacing the storage mechanism.
- `backend/app/api/routes_settings.py:85` has strict Pydantic payloads for the existing settings sections; full config editing needs compatible schema expansion.
- `main.py:106` builds the current runtime config dictionary directly from `os.getenv()` values.
- `backend/app/services/analysis_service.py:17` is the Web analysis service entrypoint and currently calls `process_message_detailed()` with no explicit config on the sync path.
- `main.py:1940` to `main.py:1966` runs the trend-prediction stage through `simulate_dashboard(self.config, event, context)`.
- `frontend/src/views/SettingsView.vue:8` currently mounts fixed tabs, and `frontend/src/api/settings.ts:49` has a fixed `AppSettings` shape.
- `.env.example` and `docs/env-vars.md` enumerate the complete environment configuration surface that should seed the full settings dictionary.

## Decisions (with rationale)
- Use the existing JSON settings file and settings API as the persistence surface; do not add a database/Redis dependency.
- Introduce a backend-owned config catalog with typed field metadata so the frontend can render every field without duplicating defaults in Vue.
- Split config fields by `effective_scope`: `runtime_immediate`, `web_restart`, `frontend_rebuild`, `compose_recreate`, and `display_only`.
- Make Web analysis call a Web-specific config loader and pass the resulting dictionary into `process_message_detailed()` so every Web-triggered trend-prediction run uses the saved config.
- Keep `main.load_config()` compatible for terminal/scripts, but let it share the same defaults/coercion helpers where doing so does not change CLI precedence.

## Scope IN
- Full `.env.example`-based config catalog with default values, type coercion, metadata, and `.env` bootstrap overlay.
- First-load persistence of the initial settings file when no settings file exists.
- Settings API support for full config dictionary reads/writes and metadata.
- Dynamic Vue config editor for all config fields plus existing specialized settings tabs.
- Web analysis/trend-prediction runtime loading from saved settings.
- Tests and manual QA evidence for bootstrap, save/reload, runtime consumption, invalid payloads, and CLI/env compatibility.

## Scope OUT (Must NOT have)
- Replacing JSON settings storage with a database.
- Making already-running Vite/server/Docker settings magically apply without rebuild/restart/recreate.
- Logging or visibly displaying secrets in clear text by default.
- Removing existing model service, notification, audit, data management, or risk-rule settings behavior.
- Broad rewrites of the CrewAI pipeline unrelated to config loading.

## Open questions
- None blocking. The plan adopts the reversible defaults above because the user explicitly requested a full execution plan in this worktree.

## Approval gate
status: approved-by-user-request
pending-action: plan written at `.omo/plans/settings-full-impl.md`
