import { Copy, Search, Sparkles, Trash2 } from 'lucide-react'
import clsx from 'clsx'

type RunStep = {
  nodeId?: string
  node_id?: string
  title: string
  status: 'done' | 'routed' | 'waiting' | 'skipped' | 'error'
  input: string
  output: string
  kind?: string | null
  variable?: string
  provider?: string
  error?: string
  duration_ms?: number
  attempt_count?: number
}

type ServerRunRecord = {
  id: string
  workflow_name: string
  input_text: string
  status: string
  steps: RunStep[]
  cost_summary?: {
    billable_step_count?: number
    cost_units?: number
    provider_breakdown?: Record<string, number>
  }
  created_at: string
}

type RunHistoryStatusFilter = 'all' | 'ok' | 'error'

type RunHistoryPanelProps = {
  runHistory: ServerRunRecord[]
  visibleRunHistory: ServerRunRecord[]
  selectedRunId: string
  selectedRunRecord?: ServerRunRecord
  runHistorySearch: string
  runHistoryStatusFilter: RunHistoryStatusFilter
  runSteps: RunStep[]
  selectedRunDoneCount: number
  selectedRunSkippedCount: number
  selectedRunErrorCount: number
  onSearchChange: (value: string) => void
  onStatusFilterChange: (value: RunHistoryStatusFilter) => void
  onSelectRunHistory: (runId: string) => void
  onDeleteRunHistory: (runId: string) => void
  onCopyCurrentRunSummary: () => void
  onCopyText: (label: string, value: string | undefined) => void
  formatProviderBreakdown: (breakdown: Record<string, number> | undefined) => string
}

const extractUrls = (value: string) => Array.from(value.matchAll(/https?:\/\/[^\s)）"'，。]+/g)).map((match) => match[0])

const extractFirstUrl = (value: string) => extractUrls(value)[0]

const isAudioStep = (step: RunStep) => step.provider?.includes('TTS') || step.output.includes('音频地址')

const isSimulatedAudioStep = (step: RunStep) =>
  step.output.includes('模拟音频') || step.output.includes('模拟生成音频') || step.error?.includes('AliyunProviderError')

const isImageUrl = (value: string) => /\.(png|jpe?g|webp|gif)(\?|$)/i.test(value)

const isFinalOutputStep = (step: RunStep) => {
  if (step.status !== 'done') return false
  const variable = step.variable ?? ''
  return (
    step.kind === 'output' ||
    /\{\{\s*(answer|final_answer|result|output)\s*\}\}/i.test(variable) ||
    /最终|回答|结果|派单|工单|输出/.test(step.title)
  )
}

const formatDuration = (durationMs: number | undefined) => {
  if (durationMs === undefined || durationMs === null) return '未记录'
  return durationMs <= 0 ? '<1ms' : `${durationMs}ms`
}

const getFinalRunOutput = (steps: RunStep[]) => {
  const successfulSteps = steps.filter((step) => step.status === 'done' && step.output?.trim())
  const finalStep = [...successfulSteps].reverse().find(isFinalOutputStep) ?? successfulSteps.at(-1)
  return finalStep
    ? {
        title: finalStep.title.replace(/^\d+\.\s*/, ''),
        output: finalStep.output,
        variable: finalStep.variable,
      }
    : null
}

export function RunHistoryPanel({
  runHistory,
  visibleRunHistory,
  selectedRunId,
  selectedRunRecord,
  runHistorySearch,
  runHistoryStatusFilter,
  runSteps,
  selectedRunDoneCount,
  selectedRunSkippedCount,
  selectedRunErrorCount,
  onSearchChange,
  onStatusFilterChange,
  onSelectRunHistory,
  onDeleteRunHistory,
  onCopyCurrentRunSummary,
  onCopyText,
  formatProviderBreakdown,
}: RunHistoryPanelProps) {
  const finalOutput = getFinalRunOutput(runSteps)

  return (
    <>
      <div className="run-history-tools">
        <label className="run-history-search">
          <Search size={14} />
          <input
            type="search"
            value={runHistorySearch}
            onChange={(event) => onSearchChange(event.target.value)}
            placeholder="搜索输入或输出"
          />
        </label>
        <select
          value={runHistoryStatusFilter}
          aria-label="运行历史状态筛选"
          onChange={(event) => onStatusFilterChange(event.target.value as RunHistoryStatusFilter)}
        >
          <option value="all">全部状态</option>
          <option value="ok">成功</option>
          <option value="error">失败</option>
        </select>
      </div>

      <div className="run-history">
        {runHistory.length === 0 ? (
          <p>暂无后端运行历史。</p>
        ) : visibleRunHistory.length === 0 ? (
          <p>没有匹配的运行历史。</p>
        ) : (
          visibleRunHistory.slice(0, 8).map((run) => {
            const hasError = run.status === 'error' || run.steps.some((step) => step.status === 'error')
            const lastStep = [...run.steps].reverse().find((step) => step.status !== 'skipped') ?? run.steps.at(-1)
            return (
              <div key={run.id} className={clsx('run-history-item', run.id === selectedRunId && 'active')}>
                <button type="button" onClick={() => onSelectRunHistory(run.id)}>
                  <strong>{run.workflow_name}</strong>
                  <span>{new Date(run.created_at).toLocaleString('zh-CN')}</span>
                  <small>{run.input_text}</small>
                  <small>
                    估算成本 {run.cost_summary?.cost_units ?? 0} · 计费节点{' '}
                    {run.cost_summary?.billable_step_count ?? 0}
                  </small>
                  <small>{lastStep ? `结果：${lastStep.output}` : '暂无节点输出'}</small>
                </button>
                <span className={clsx('run-status-badge', hasError ? 'error' : 'ok')}>
                  {hasError ? '失败' : '成功'}
                </span>
                <button
                  type="button"
                  className="run-delete-button"
                  aria-label="删除运行历史"
                  onClick={() => onDeleteRunHistory(run.id)}
                >
                  <Trash2 size={14} />
                </button>
              </div>
            )
          })
        )}
      </div>

      <div className="run-log">
        {runSteps.length === 0 ? (
          <div className="empty-run">
            <Sparkles size={18} />
            <span>点击运行后，可以查看每个节点的模拟输出。</span>
          </div>
        ) : (
          <>
            <div className="run-summary">
              <div>
                <strong>{selectedRunRecord ? selectedRunRecord.workflow_name : '当前运行结果'}</strong>
                <span>
                  完成 {selectedRunDoneCount || runSteps.filter((step) => step.status === 'done' || step.status === 'routed').length}
                  个，跳过 {selectedRunSkippedCount || runSteps.filter((step) => step.status === 'skipped').length} 个，错误{' '}
                  {selectedRunErrorCount || runSteps.filter((step) => step.status === 'error').length} 个
                </span>
                {selectedRunRecord?.cost_summary && (
                  <small>
                    估算成本 {selectedRunRecord.cost_summary.cost_units ?? 0} · 计费节点{' '}
                    {selectedRunRecord.cost_summary.billable_step_count ?? 0} ·{' '}
                    {formatProviderBreakdown(selectedRunRecord.cost_summary.provider_breakdown)}
                  </small>
                )}
              </div>
              <button type="button" onClick={onCopyCurrentRunSummary}>
                <Copy size={12} />
                复制整次结果
              </button>
            </div>
            {finalOutput && (
              <section className="final-run-output">
                <div className="final-run-output-header">
                  <div>
                    <span>最终结果</span>
                    <strong>{finalOutput.title}</strong>
                  </div>
                  <button type="button" onClick={() => onCopyText('最终结果', finalOutput.output)}>
                    <Copy size={12} />
                    复制
                  </button>
                </div>
                <pre>{finalOutput.output}</pre>
                {finalOutput.variable && <small>写入变量：{finalOutput.variable}</small>}
              </section>
            )}
            {runSteps.map((step) => {
              const stepId = step.nodeId ?? step.node_id ?? step.title
              const outputUrl = extractFirstUrl(step.output)
              const audioUrl = outputUrl && isAudioStep(step) ? outputUrl : ''
              const imageUrls = [...new Set(extractUrls(step.output).filter(isImageUrl))]
              const simulatedAudio = !audioUrl && isSimulatedAudioStep(step)
              return (
                <article key={stepId}>
                  <span className={clsx('status-dot', step.status)} />
                  <div>
                    <strong>{step.title}</strong>
                    <div className="run-step-meta">
                      {step.kind && <span>{step.kind}</span>}
                      {step.provider && <span>来源 {step.provider}</span>}
                      <span>耗时 {formatDuration(step.duration_ms)}</span>
                      <span>尝试 {step.attempt_count ?? 1} 次</span>
                    </div>
                    <dl>
                      <div>
                        <dt>
                          输入
                          <button type="button" onClick={() => onCopyText('节点输入', step.input)}>
                            <Copy size={12} />
                            复制
                          </button>
                        </dt>
                        <dd>{step.input}</dd>
                      </div>
                      <div>
                        <dt>
                          输出
                          <button type="button" onClick={() => onCopyText('节点输出', step.output)}>
                            <Copy size={12} />
                            复制
                          </button>
                        </dt>
                        <dd>{step.output}</dd>
                      </div>
                      {audioUrl && (
                        <div className="audio-output">
                          <dt>音频播放</dt>
                          <dd>
                            <audio controls src={audioUrl}>
                              当前浏览器不支持音频播放。
                            </audio>
                            <div className="audio-output-actions">
                              <a href={audioUrl} target="_blank" rel="noreferrer">
                                打开音频
                              </a>
                              <button type="button" onClick={() => onCopyText('音频链接', audioUrl)}>
                                <Copy size={12} />
                                复制链接
                              </button>
                            </div>
                          </dd>
                        </div>
                      )}
                      {simulatedAudio && (
                        <div className="audio-output unavailable">
                          <dt>音频播放</dt>
                          <dd>
                            这次没有生成真实音频文件。当前节点使用了模拟音频或调用失败回退，重新运行成功后这里会显示播放器和打开按钮。
                          </dd>
                        </div>
                      )}
                      {imageUrls.length > 0 && (
                        <div className="image-output">
                          <dt>图片预览</dt>
                          <dd>
                            <div className="image-output-grid">
                              {imageUrls.map((imageUrl, imageIndex) => (
                                <figure key={imageUrl}>
                                  <a href={imageUrl} target="_blank" rel="noreferrer">
                                    <img src={imageUrl} alt={`生成图片 ${imageIndex + 1}`} loading="lazy" />
                                  </a>
                                  <figcaption>
                                    <a href={imageUrl} target="_blank" rel="noreferrer">
                                      打开图片
                                    </a>
                                    <button type="button" onClick={() => onCopyText('图片链接', imageUrl)}>
                                      <Copy size={12} />
                                      复制链接
                                    </button>
                                  </figcaption>
                                </figure>
                              ))}
                            </div>
                          </dd>
                        </div>
                      )}
                      {step.variable && (
                        <div>
                          <dt>写入</dt>
                          <dd>{step.variable}</dd>
                        </div>
                      )}
                      {step.provider && (
                        <div>
                          <dt>来源</dt>
                          <dd>{step.provider}</dd>
                        </div>
                      )}
                      {step.error && (
                        <div className="run-error-detail">
                          <dt>
                            错误原因
                            <button type="button" onClick={() => onCopyText('错误原因', step.error)}>
                              <Copy size={12} />
                              复制
                            </button>
                          </dt>
                          <dd>{step.error}</dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </article>
              )
            })}
          </>
        )}
      </div>
    </>
  )
}
