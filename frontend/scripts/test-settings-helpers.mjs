import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const tempDir = await mkdtemp(join(tmpdir(), 'sentinel-settings-helpers-'))
const outputFile = join(tempDir, 'settingsHelpers.mjs')

try {
  const source = await readFile(resolve('src/views/settings/helpers.ts'), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  })
  await writeFile(outputFile, compiled.outputText)

  const {
    buildConfigGroups,
    formatSystemDate,
    normalizeRuntimeFieldValue,
    parseListEditorValue,
    runtimeScopeLabel,
    serializeListEditorValue,
    modelTestFeedback,
    notificationTestFeedback,
  } = await import(pathToFileURL(outputFile).href)

  assert.deepEqual(
    modelTestFeedback({ success: false, message: '模型服务不可达', endpoint: 'http://demo.test' }),
    { kind: 'error', message: '模型服务不可达' },
  )
  assert.deepEqual(
    modelTestFeedback({ success: true, message: '模型服务连接成功', endpoint: 'http://demo.test' }),
    { kind: 'notice', message: '模型服务连接成功' },
  )
  assert.deepEqual(
    notificationTestFeedback({ success: false, message: 'Webhook 不可达', channel: 'Webhook' }),
    { kind: 'error', message: 'Webhook 不可达' },
  )
  assert.deepEqual(
    notificationTestFeedback({ success: true, message: 'Webhook 测试发送成功', channel: 'Webhook' }),
    { kind: 'notice', message: 'Webhook 测试发送成功' },
  )
  assert.equal(
    formatSystemDate(
      new Date('2026-06-14T15:04:05+08:00'),
      { timezone: 'Asia/Shanghai (UTC+08:00)', dateFormat: 'YYYY-MM-DD HH:mm:ss', language: '简体中文' },
    ),
    '2026-06-14 15:04:05',
  )

  assert.equal(runtimeScopeLabel('runtime_immediate'), '即时生效')
  assert.equal(runtimeScopeLabel('web_restart'), '需重启后端')
  assert.equal(runtimeScopeLabel('frontend_rebuild'), '需重建前端')
  assert.equal(runtimeScopeLabel('compose_recreate'), '需重建依赖服务')
  assert.equal(runtimeScopeLabel('display_only'), '只读展示')
  assert.equal(runtimeScopeLabel('unknown-scope'), '需额外处理')

  assert.deepEqual(parseListEditorValue(' alpha, beta\n\ngamma \n alpha '), ['alpha', 'beta', 'gamma'])
  assert.equal(serializeListEditorValue(['alpha', 'beta', 'gamma']), 'alpha\nbeta\ngamma')

  assert.equal(
    normalizeRuntimeFieldValue({ scalar_type: 'bool' }, true),
    true,
  )
  assert.equal(
    normalizeRuntimeFieldValue({ scalar_type: 'int' }, 12.6),
    12,
  )
  assert.equal(
    normalizeRuntimeFieldValue({ scalar_type: 'float' }, 12),
    12,
  )
  assert.equal(
    normalizeRuntimeFieldValue({ scalar_type: 'string' }, 'bolt://localhost:7687'),
    'bolt://localhost:7687',
  )
  assert.deepEqual(
    normalizeRuntimeFieldValue({ scalar_type: 'list' }, ['aml', 'fraud']),
    ['aml', 'fraud'],
  )

  const configGroups = buildConfigGroups(
    {
      LLM_MODEL: 'qwen3.5',
      RAGFLOW_ENABLED: true,
      RAGFLOW_DATASET_IDS: ['alpha', 'beta'],
      LLM_API_KEY: '********',
    },
    [
      {
        env: 'LLM_MODEL',
        group: 'llm_base',
        key_path: 'runtime_config.LLM_MODEL',
        label: '基础模型',
        help: '主模型标识',
        scalar_type: 'string',
        default: 'qwen3.5',
        secret: false,
        editable: true,
        effective_scope: 'web_restart',
      },
      {
        env: 'LLM_API_KEY',
        group: 'llm_base',
        key_path: 'runtime_config.LLM_API_KEY',
        label: '模型密钥',
        help: '主模型密钥',
        scalar_type: 'string',
        default: '',
        secret: true,
        editable: true,
        effective_scope: 'runtime_immediate',
      },
      {
        env: 'RAGFLOW_ENABLED',
        group: 'ragflow_runtime',
        key_path: 'runtime_config.RAGFLOW_ENABLED',
        label: '启用 RAGFlow',
        help: '开启混合检索',
        scalar_type: 'bool',
        default: false,
        secret: false,
        editable: true,
        effective_scope: 'runtime_immediate',
      },
      {
        env: 'RAGFLOW_DATASET_IDS',
        group: 'ragflow_runtime',
        key_path: 'runtime_config.RAGFLOW_DATASET_IDS',
        label: '数据集列表',
        help: '多数据集配置',
        scalar_type: 'list',
        default: [],
        secret: false,
        editable: true,
        effective_scope: 'runtime_immediate',
      },
    ],
    'rag llm_api_key',
  )

  assert.equal(configGroups.length, 2)
  assert.equal(configGroups[0].group, 'llm_base')
  assert.equal(configGroups[0].matches, 1)
  assert.equal(configGroups[1].group, 'ragflow_runtime')
  assert.equal(configGroups[1].fields.length, 2)
  assert.deepEqual(configGroups[1].fields[1].value, ['alpha', 'beta'])
  assert.equal(configGroups[0].fields[0].scopeLabel, '即时生效')
} finally {
  await rm(tempDir, { recursive: true, force: true })
}
