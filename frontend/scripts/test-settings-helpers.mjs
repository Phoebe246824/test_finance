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
    formatSystemDate,
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
} finally {
  await rm(tempDir, { recursive: true, force: true })
}
