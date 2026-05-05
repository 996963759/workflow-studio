import { TerminalSquare } from 'lucide-react'

type RunStep = {
  status: string
  error?: string | null
}

type ServerRunRecord = {
  id: string
  workflow_name: string
  steps: RunStep[]
  created_at: string
}

type AuditLogRecord = {
  id: string
  actor_username: string
  summary: string
  created_at: string
}

type RunJobRecord = {
  id: string
  status: string
  updated_at: string
}

type AdminOverviewRecord = {
  database: string
  queue_backend: string
  workspace: {
    name: string
    role: string
  }
  counts: Record<string, number>
  settings: {
    app_env?: string
    session_ttl_hours?: number
    workspace_invitation_ttl_hours?: number
    run_job_workers?: number
    external_rag_enabled?: boolean
    cors_origins?: string[]
    model_config_secret_configured?: boolean
  }
  provider_status: {
    deepseek_configured: boolean
    aliyun_configured?: boolean
  }
  knowledge_status: {
    document_count: number
  }
  run_metrics: {
    sampled_runs: number
    ok_runs: number
    error_runs: number
    success_rate: number
    average_duration_ms: number
    average_step_count: number
    billable_step_count: number
    total_cost_units: number
    average_cost_units: number
    provider_breakdown: Record<string, number>
    recent_failed_runs: ServerRunRecord[]
  }
  recent_audit_logs: AuditLogRecord[]
  recent_run_jobs: RunJobRecord[]
}

type AdminOverviewPanelProps = {
  overview: AdminOverviewRecord | null
  busy: boolean
  onRefresh: () => void
  formatProviderBreakdown: (breakdown: Record<string, number> | undefined) => string
}

export function AdminOverviewPanel({
  overview,
  busy,
  onRefresh,
  formatProviderBreakdown,
}: AdminOverviewPanelProps) {
  return (
    <section className="panel admin-overview-panel">
      <div className="panel-title between">
        <span>
          <TerminalSquare size={16} />
          系统概览
        </span>
        <button type="button" className="mini-action" disabled={busy} onClick={onRefresh}>
          {busy ? '刷新中...' : '刷新'}
        </button>
      </div>
      {overview ? (
        <>
          <div className="admin-overview-grid">
            <div>
              <span>数据库</span>
              <strong>{overview.database}</strong>
            </div>
            <div>
              <span>队列</span>
              <strong>{overview.queue_backend}</strong>
            </div>
            <div>
              <span>成员</span>
              <strong>{overview.counts.members ?? 0}</strong>
            </div>
            <div>
              <span>待用邀请</span>
              <strong>{overview.counts.pending_invitations ?? 0}</strong>
            </div>
            <div>
              <span>工作流</span>
              <strong>{overview.counts.workflows ?? 0}</strong>
            </div>
            <div>
              <span>运行记录</span>
              <strong>{overview.counts.runs ?? 0}</strong>
            </div>
            <div>
              <span>排队任务</span>
              <strong>{overview.counts.queued_run_jobs ?? 0}</strong>
            </div>
            <div>
              <span>失败任务</span>
              <strong>{overview.counts.failed_run_jobs ?? 0}</strong>
            </div>
            <div>
              <span>成功率</span>
              <strong>{overview.run_metrics.success_rate}%</strong>
            </div>
            <div>
              <span>平均耗时</span>
              <strong>{overview.run_metrics.average_duration_ms}ms</strong>
            </div>
            <div>
              <span>平均节点</span>
              <strong>{overview.run_metrics.average_step_count}</strong>
            </div>
            <div>
              <span>失败运行</span>
              <strong>{overview.run_metrics.error_runs}</strong>
            </div>
            <div>
              <span>估算成本</span>
              <strong>{overview.run_metrics.total_cost_units}</strong>
            </div>
            <div>
              <span>平均成本</span>
              <strong>{overview.run_metrics.average_cost_units}</strong>
            </div>
            <div>
              <span>计费节点</span>
              <strong>{overview.run_metrics.billable_step_count}</strong>
            </div>
          </div>
          <div className="admin-overview-list">
            <article className="admin-health-row">
              <strong>运行健康</strong>
              <span>
                最近 {overview.run_metrics.sampled_runs} 次采样 · 成功 {overview.run_metrics.ok_runs} · 失败{' '}
                {overview.run_metrics.error_runs}
              </span>
            </article>
            <article className="admin-cost-row">
              <strong>成本估算</strong>
              <span>
                总成本单位 {overview.run_metrics.total_cost_units} · 平均 {overview.run_metrics.average_cost_units} ·{' '}
                {formatProviderBreakdown(overview.run_metrics.provider_breakdown)}
              </span>
            </article>
            <article>
              <strong>模型与知识库</strong>
              <span>
                DeepSeek {overview.provider_status.deepseek_configured ? '已配置' : '未配置'} · 阿里云{' '}
                {overview.provider_status.aliyun_configured ? '已配置' : '未配置'} · 知识文档{' '}
                {overview.knowledge_status.document_count}
              </span>
            </article>
            <article>
              <strong>当前空间</strong>
              <span>
                {overview.workspace.name} · {overview.workspace.role}
              </span>
            </article>
            <article>
              <strong>安全配置</strong>
              <span>
                登录 {overview.settings.session_ttl_hours ?? '-'} 小时 · 邀请{' '}
                {overview.settings.workspace_invitation_ttl_hours ?? '-'} 小时 · 密钥保护{' '}
                {overview.settings.model_config_secret_configured ? '已启用' : '未启用'}
              </span>
            </article>
            <article>
              <strong>运行配置</strong>
              <span>
                {overview.settings.app_env ?? 'development'} · Worker {overview.settings.run_job_workers ?? 0} · RAG{' '}
                {overview.settings.external_rag_enabled ? '已启用' : '未启用'}
              </span>
            </article>
            <article>
              <strong>访问来源</strong>
              <span>{overview.settings.cors_origins?.join(', ') || '未配置'}</span>
            </article>
            {overview.recent_audit_logs.slice(0, 3).map((log) => (
              <article key={log.id}>
                <strong>{log.summary}</strong>
                <span>
                  {log.actor_username} · {new Date(log.created_at).toLocaleString('zh-CN')}
                </span>
              </article>
            ))}
            {overview.recent_run_jobs.slice(0, 3).map((job) => (
              <article key={job.id}>
                <strong>任务 {job.status}</strong>
                <span>{new Date(job.updated_at).toLocaleString('zh-CN')}</span>
              </article>
            ))}
            {overview.run_metrics.recent_failed_runs.map((run) => (
              <article key={run.id} className="admin-failed-run">
                <strong>{run.workflow_name}</strong>
                <span>
                  最近失败 · {run.steps.find((step) => step.status === 'error')?.error ?? '未记录错误原因'} ·{' '}
                  {new Date(run.created_at).toLocaleString('zh-CN')}
                </span>
              </article>
            ))}
          </div>
        </>
      ) : (
        <p className="model-status-note">点击刷新读取当前团队空间的系统概览。</p>
      )}
    </section>
  )
}
