import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import ts from 'typescript'

const tempDir = await mkdtemp(join(tmpdir(), 'sentinel-progress-display-'))
const outputFile = join(tempDir, 'progressDisplay.mjs')

try {
  const source = await readFile(resolve('src/utils/progressDisplay.ts'), 'utf8')
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.ESNext,
      target: ts.ScriptTarget.ES2022,
      verbatimModuleSyntax: true,
    },
  })
  await writeFile(outputFile, compiled.outputText)

  const { progressAriaLabel, progressCounterText, progressPercent } = await import(
    pathToFileURL(outputFile).href
  )
  const progress = {
    stage_key: 'single_graph',
    stage_label: '单条构图',
    stage_index: 5,
    stage_total: 12,
    stage_detail: '正在把当前事件写入知识图谱',
  }

  assert.equal(progressPercent(null), 0)
  assert.equal(progressPercent(progress), 42)
  assert.equal(progressPercent({ ...progress, stage_index: 18 }), 100)
  assert.equal(progressCounterText({ title: '单次分析进度', progress }), '5 / 12')
  assert.equal(progressCounterText({ title: '批量分析进度', progress, batchIndex: 0, batchTotal: 3 }), '5 / 12')
  assert.equal(progressCounterText({ title: '批量分析进度', progress, batchIndex: 1, batchTotal: 3 }), '第 1 / 3 条')
  assert.equal(progressCounterText({ title: '批量分析进度', progress, batchIndex: 4, batchTotal: 3 }), '第 3 / 3 条')
  assert.equal(
    progressAriaLabel({ title: '批量分析进度', progress, batchIndex: 2, batchTotal: 3 }),
    '批量分析进度：单条构图，第 2 / 3 条',
  )
} finally {
  await rm(tempDir, { recursive: true, force: true })
}
