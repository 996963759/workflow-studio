import { useEffect, useMemo, useState } from 'react'
import { RefreshCcw, Play, Plus, Sparkles, Trash2 } from 'lucide-react'

type EvaluationCaseRecord = {
  id: string
  input_text: string
  expected_output: string
  expected_keywords: string[]
  created_at: string
  updated_at: string
}

type EvaluationDatasetRecord = {
  id: string
  name: string
  description: string
  case_count: number
  created_at: string
  updated_at: string
  cases: EvaluationCaseRecord[]
}

type EvaluationCaseResult = {
  case_id: string
  input_text: string
  expected_keywords: string[]
  output: string
  passed: boolean
  missing_keywords: string[]
  status: string
  duration_ms: number
  run_id?: string | null
  error?: string | null
}

type EvaluationRunRecord = {
  id: string
  dataset_id: string
  dataset_name: string
  workflow_id: string
  workflow_name: string
  status: string
  total_cases: number
  passed_cases: number
  failed_cases: number
  pass_rate: number
  average_duration_ms: number
  created_by: string
  created_at: string
  results: EvaluationCaseResult[]
}

type EvaluationPanelProps = {
  apiFetch: (path: string, init?: RequestInit) => Promise<Response>
  currentWorkflowId?: string
  currentWorkflowName?: string
  onNotice: (message: string) => void
}

type DatasetFormCase = {
  inputText: string
  expectedOutput: string
  expectedKeywordsText: string
}

const newCase = (): DatasetFormCase => ({
  inputText: '请帮我总结这段内容。',
  expectedOutput: '',
  expectedKeywordsText: '总结',
})

const emptyDataset = () => ({
  id: '',
  name: '新评测集',
  description: '用于轻量评测工作流效果。',
  cases: [newCase()],
})

const parseKeywords = (text: string) =>
  text
    .split(/[\n,，]/)
    .map((keyword) => keyword.trim())
    .filter(Boolean)

export function EvaluationPanel({ apiFetch, currentWorkflowId, currentWorkflowName, onNotice }: EvaluationPanelProps) {
  const [datasets, setDatasets] = useState<EvaluationDatasetRecord[]>([])
  const [runs, setRuns] = useState<EvaluationRunRecord[]>([])
  const [selectedDatasetId, setSelectedDatasetId] = useState('')
  const [form, setForm] = useState(emptyDataset())
  const [busy, setBusy] = useState<'load' | 'save' | 'delete' | 'run' | null>(null)
  const [feedback, setFeedback] = useState('')
  const [selectedRunId, setSelectedRunId] = useState('')

  const selectedDataset = useMemo(
    () => datasets.find((dataset) => dataset.id === selectedDatasetId) ?? null,
    [datasets, selectedDatasetId],
  )
  const selectedRun = useMemo(() => runs.find((run) => run.id === selectedRunId) ?? null, [runs, selectedRunId])

  const loadDatasets = async () => {
    setBusy('load')
    try {
      const response = await apiFetch('/api/evaluations/datasets')
      if (!response.ok) throw new Error('load datasets failed')
      const records = (await response.json()) as EvaluationDatasetRecord[]
      setDatasets(records)
      const nextSelectedId = records.find((dataset) => dataset.id === selectedDatasetId)?.id ?? records[0]?.id ?? ''
      setSelectedDatasetId(nextSelectedId)
      setFeedback(records.length > 0 ? `已读取 ${records.length} 个评测集。` : '当前还没有评测集。')
      if (!nextSelectedId) {
        setForm(emptyDataset())
      }
      await loadRuns(nextSelectedId)
    } catch {
      setDatasets([])
      setRuns([])
      setSelectedDatasetId('')
      setForm(emptyDataset())
      setFeedback('读取评测集失败，请确认后端在线。')
    } finally {
      setBusy(null)
    }
  }

  const loadDataset = async (datasetId: string) => {
    if (!datasetId) {
      setSelectedDatasetId('')
      setForm(emptyDataset())
      return
    }
    const response = await apiFetch(`/api/evaluations/datasets/${datasetId}`)
    if (!response.ok) throw new Error('load dataset failed')
    const dataset = (await response.json()) as EvaluationDatasetRecord
    setSelectedDatasetId(dataset.id)
    setForm({
      id: dataset.id,
      name: dataset.name,
      description: dataset.description,
      cases: dataset.cases.length > 0 ? dataset.cases.map((item) => ({
        inputText: item.input_text,
        expectedOutput: item.expected_output,
        expectedKeywordsText: item.expected_keywords.join('\n'),
      })) : [newCase()],
    })
  }

  const loadRuns = async (datasetId = selectedDatasetId) => {
    const response = await apiFetch(datasetId ? `/api/evaluations/runs?dataset_id=${datasetId}` : '/api/evaluations/runs')
    if (!response.ok) throw new Error('load evaluation runs failed')
    const records = (await response.json()) as EvaluationRunRecord[]
    setRuns(records)
    setSelectedRunId((current) => current || records[0]?.id || '')
  }

  const resetForm = () => {
    setSelectedDatasetId('')
    setForm(emptyDataset())
    setFeedback('已切换到新评测集。')
  }

  const updateCase = (index: number, patch: Partial<DatasetFormCase>) => {
    setForm((current) => ({
      ...current,
      cases: current.cases.map((item, itemIndex) => (itemIndex === index ? { ...item, ...patch } : item)),
    }))
  }

  const addCase = () => setForm((current) => ({ ...current, cases: [...current.cases, newCase()] }))

  const removeCase = (index: number) => {
    setForm((current) => ({
      ...current,
      cases: current.cases.length > 1 ? current.cases.filter((_, itemIndex) => itemIndex !== index) : [newCase()],
    }))
  }

  const persistDataset = async () => {
    setBusy('save')
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        cases: form.cases.map((item) => ({
          input_text: item.inputText.trim(),
          expected_output: item.expectedOutput.trim(),
          expected_keywords: parseKeywords(item.expectedKeywordsText),
        })),
      }
      const method = form.id ? 'PUT' : 'POST'
      const path = form.id ? `/api/evaluations/datasets/${form.id}` : '/api/evaluations/datasets'
      const response = await apiFetch(path, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error('save dataset failed')
      const dataset = (await response.json()) as EvaluationDatasetRecord
      setDatasets((current) => {
        const next = current.filter((item) => item.id !== dataset.id)
        return [dataset, ...next]
      })
      await loadDataset(dataset.id)
      await loadRuns(dataset.id)
      setFeedback(`已${form.id ? '更新' : '创建'}评测集「${dataset.name}」。`)
      onNotice(`评测集已${form.id ? '更新' : '创建'}。`)
    } catch {
      setFeedback('保存评测集失败，请检查内容后重试。')
    } finally {
      setBusy(null)
    }
  }

  const deleteDataset = async () => {
    if (!selectedDatasetId) return
    setBusy('delete')
    try {
      const response = await apiFetch(`/api/evaluations/datasets/${selectedDatasetId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('delete dataset failed')
      setDatasets((current) => current.filter((item) => item.id !== selectedDatasetId))
      setRuns((current) => current.filter((item) => item.dataset_id !== selectedDatasetId))
      resetForm()
      onNotice('评测集已删除。')
    } catch {
      setFeedback('删除评测集失败。')
    } finally {
      setBusy(null)
    }
  }

  const runDataset = async () => {
    if (!selectedDatasetId || !currentWorkflowId) return
    setBusy('run')
    try {
      const response = await apiFetch(`/api/evaluations/datasets/${selectedDatasetId}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ workflow_id: currentWorkflowId }),
      })
      if (!response.ok) throw new Error('run dataset failed')
      const run = (await response.json()) as EvaluationRunRecord
      setRuns((current) => [run, ...current.filter((item) => item.id !== run.id)])
      setSelectedRunId(run.id)
      setFeedback(`已完成评测：通过 ${run.passed_cases}/${run.total_cases}，通过率 ${run.pass_rate}%。`)
      onNotice(`评测已完成：${run.passed_cases}/${run.total_cases}`)
    } catch {
      setFeedback('评测运行失败，请确认当前工作流已同步到后端并且没有严重问题。')
    } finally {
      setBusy(null)
    }
  }

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDatasets()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (selectedDatasetId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      void loadDataset(selectedDatasetId)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDatasetId])

  useEffect(() => {
    if (selectedDatasetId) {
      void loadRuns(selectedDatasetId).catch(() => undefined)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedDatasetId])

  return (
    <section className="panel evaluation-panel">
      <div className="panel-title between">
        <span>
          <Sparkles size={16} />
          评测
        </span>
        <button type="button" className="mini-action" disabled={busy === 'load'} onClick={() => void loadDatasets()}>
          <RefreshCcw size={13} />
          刷新
        </button>
      </div>
      <p className="inspector-note">
        轻量版评测只做关键词校验和运行留痕，适合先验证工作流是否朝着预期方向输出。
      </p>

      <label>
        评测集
        <select value={selectedDatasetId} onChange={(event) => setSelectedDatasetId(event.target.value)}>
          <option value="">新建评测集</option>
          {datasets.map((dataset) => (
            <option key={dataset.id} value={dataset.id}>
              {dataset.name} ({dataset.case_count})
            </option>
          ))}
        </select>
      </label>

      <div className="evaluation-summary">
        <span>当前工作流：{currentWorkflowName}</span>
        <span>评测集：{selectedDataset ? `${selectedDataset.case_count} 条样例` : '未选择'}</span>
      </div>

      <label>
        评测集名称
        <input value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
      </label>
      <label>
        描述
        <textarea
          rows={3}
          value={form.description}
          onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))}
        />
      </label>

      <div className="evaluation-case-list">
        {form.cases.map((item, index) => (
          <article key={index} className="evaluation-case-row">
            <div className="panel-title between">
              <span>样例 {index + 1}</span>
              <button type="button" className="icon-button" onClick={() => removeCase(index)} aria-label={`删除样例 ${index + 1}`}>
                <Trash2 size={14} />
              </button>
            </div>
            <label>
              输入
              <textarea
                rows={3}
                value={item.inputText}
                onChange={(event) => updateCase(index, { inputText: event.target.value })}
              />
            </label>
            <label>
              期望输出说明
              <textarea
                rows={2}
                value={item.expectedOutput}
                onChange={(event) => updateCase(index, { expectedOutput: event.target.value })}
              />
            </label>
            <label>
              期望关键词
              <textarea
                rows={2}
                value={item.expectedKeywordsText}
                onChange={(event) => updateCase(index, { expectedKeywordsText: event.target.value })}
                placeholder="退款\n客服"
              />
            </label>
          </article>
        ))}
      </div>

      <div className="runner-actions">
        <button type="button" onClick={addCase}>
          <Plus size={14} />
          添加样例
        </button>
        <button type="button" onClick={() => void persistDataset()} disabled={busy === 'save'}>
          保存
        </button>
        <button type="button" onClick={resetForm} disabled={busy !== null}>
          新建
        </button>
        <button type="button" onClick={() => void runDataset()} disabled={!selectedDatasetId || !currentWorkflowId || busy === 'run'}>
          <Play size={14} />
          运行评测
        </button>
        <button type="button" onClick={() => void deleteDataset()} disabled={!selectedDatasetId || busy === 'delete'}>
          删除
        </button>
      </div>

      {feedback && <p className="model-status-note">{feedback}</p>}

      <div className="evaluation-runs">
        <div className="panel-title">
          <span>评测历史</span>
        </div>
        {runs.length === 0 ? (
          <p className="model-status-note">暂无评测历史。</p>
        ) : (
          runs.map((run) => (
            <article key={run.id} className={selectedRunId === run.id ? 'evaluation-run active' : 'evaluation-run'}>
              <button type="button" onClick={() => setSelectedRunId(run.id)}>
                <strong>{run.dataset_name}</strong>
                <small>
                  {run.passed_cases}/{run.total_cases} · {run.pass_rate}% · {new Date(run.created_at).toLocaleString('zh-CN')}
                </small>
              </button>
            </article>
          ))
        )}
      </div>

      {selectedRun && (
        <div className="evaluation-run-detail">
          <div className="panel-title">
            <span>最新结果</span>
          </div>
          <p className="model-status-note">
            {selectedRun.workflow_name} · {selectedRun.status} · 平均 {selectedRun.average_duration_ms}ms
          </p>
          {selectedRun.results.map((result) => (
            <article key={result.case_id} className="evaluation-result-row">
              <strong>{result.passed ? '通过' : '未通过'}</strong>
              <span>
                输入：{result.input_text}
              </span>
              <span>
                输出：{result.output || '无输出'}
              </span>
              {!result.passed && result.missing_keywords.length > 0 && (
                <span>缺少关键词：{result.missing_keywords.join('、')}</span>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  )
}
