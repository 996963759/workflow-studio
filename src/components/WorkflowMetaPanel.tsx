import { Archive } from 'lucide-react'
import clsx from 'clsx'

type WorkflowSyncState = 'local' | 'synced' | 'dirty'
type WorkflowPublishStatus = 'draft' | 'published' | 'changed'
type WorkflowMetaBusy = 'versions' | 'audit' | 'save-version' | 'restore' | 'publish' | 'diff' | null

type WorkflowVersionSummary = {
  id: string
  workflow_id: string
  sequence: number
  name: string
  version: string
  nodes: unknown
  edges: unknown
  archived: boolean
  note?: string | null
  is_published?: boolean
  created_by: string
  created_at: string
}

type WorkflowVersionDiffItem = {
  category: 'workflow' | 'node' | 'edge'
  change: 'added' | 'removed' | 'changed'
  label: string
  before?: string | null
  after?: string | null
}

type WorkflowVersionDiffResponse = {
  base_version: WorkflowVersionSummary
  target_version: WorkflowVersionSummary
  summary: Record<string, number>
  changes: WorkflowVersionDiffItem[]
}

type AuditLogRecord = {
  id: string
  actor_username: string
  summary: string
  created_at: string
}

type WorkflowMetaPanelProps<TVersion extends WorkflowVersionSummary> = {
  serverId?: string
  syncState: WorkflowSyncState
  publishStatus: WorkflowPublishStatus
  publishedAt?: string | null
  busy: WorkflowMetaBusy
  versionNote: string
  workflowVersions: TVersion[]
  orderedVersionOptions: TVersion[]
  versionDiffBaseId: string
  versionDiffTargetId: string
  versionDiff: WorkflowVersionDiffResponse | null
  auditLogs: AuditLogRecord[]
  onLoadVersions: () => void
  onLoadAuditLogs: () => void
  onVersionNoteChange: (value: string) => void
  onSaveVersion: () => void
  onPublish: () => void
  onRestoreVersion: (version: TVersion) => void
  onVersionDiffBaseChange: (value: string) => void
  onVersionDiffTargetChange: (value: string) => void
  onCompareVersions: () => void
}

const workflowPublishLabels: Record<WorkflowPublishStatus, string> = {
  draft: '草稿',
  published: '已发布',
  changed: '发布后有改动',
}

const versionDiffChangeLabels: Record<WorkflowVersionDiffItem['change'], string> = {
  added: '新增',
  removed: '删除',
  changed: '变更',
}

const versionDiffCategoryLabels: Record<WorkflowVersionDiffItem['category'], string> = {
  workflow: '工作流',
  node: '节点',
  edge: '连线',
}

export function WorkflowMetaPanel<TVersion extends WorkflowVersionSummary>({
  serverId,
  syncState,
  publishStatus,
  publishedAt,
  busy,
  versionNote,
  workflowVersions,
  orderedVersionOptions,
  versionDiffBaseId,
  versionDiffTargetId,
  versionDiff,
  auditLogs,
  onLoadVersions,
  onLoadAuditLogs,
  onVersionNoteChange,
  onSaveVersion,
  onPublish,
  onRestoreVersion,
  onVersionDiffBaseChange,
  onVersionDiffTargetChange,
  onCompareVersions,
}: WorkflowMetaPanelProps<TVersion>) {
  const hasBusyAction = Boolean(busy)
  const hasDirtyChanges = syncState === 'dirty'

  return (
    <section className="panel workflow-meta-panel">
      <div className="panel-title between">
        <span>
          <Archive size={16} />
          版本与审计
        </span>
        <div className="workflow-meta-actions">
          <button type="button" className="mini-action" disabled={!serverId || hasBusyAction} onClick={onLoadVersions}>
            {busy === 'versions' ? '刷新中...' : '版本'}
          </button>
          <button type="button" className="mini-action" disabled={!serverId || hasBusyAction} onClick={onLoadAuditLogs}>
            {busy === 'audit' ? '刷新中...' : '审计'}
          </button>
        </div>
      </div>
      {!serverId ? (
        <p className="model-status-note">当前工作流还没有同步到后端，暂无版本历史和审计记录。</p>
      ) : (
        <>
          <label className="version-note-input">
            版本备注
            <input
              value={versionNote}
              onChange={(event) => onVersionNoteChange(event.target.value)}
              placeholder="例如：面试演示稳定版，也会用于发布备注"
            />
          </label>
          <div className={clsx('publish-status-card', publishStatus)}>
            <span>发布状态</span>
            <strong>{workflowPublishLabels[publishStatus]}</strong>
            <small>
              {publishedAt
                ? `上次发布：${new Date(publishedAt).toLocaleString('zh-CN')}`
                : '还没有发布过，发布后会生成一个可标记的稳定版本。'}
            </small>
          </div>
          <div className="workflow-version-buttons">
            <button
              type="button"
              className="workflow-version-save"
              disabled={hasBusyAction || hasDirtyChanges}
              onClick={onSaveVersion}
            >
              {busy === 'save-version' ? '保存中...' : '保存当前版本'}
            </button>
            <button
              type="button"
              className="workflow-publish-button"
              disabled={hasBusyAction || hasDirtyChanges}
              onClick={onPublish}
            >
              {busy === 'publish' ? '发布中...' : '发布当前版本'}
            </button>
          </div>
          <div className="workflow-version-list">
            {workflowVersions.length === 0 ? (
              <p>暂无版本记录。</p>
            ) : (
              workflowVersions.slice(0, 5).map((version) => (
                <article key={version.id}>
                  <div>
                    <strong>
                      版本 #{version.sequence}
                      {version.is_published ? ' · 已发布' : ''}
                    </strong>
                    <span>{new Date(version.created_at).toLocaleString('zh-CN')}</span>
                    <small>{version.note || version.name}</small>
                  </div>
                  <button type="button" disabled={hasBusyAction || hasDirtyChanges} onClick={() => onRestoreVersion(version)}>
                    恢复
                  </button>
                </article>
              ))
            )}
          </div>
          <div className="workflow-version-diff">
            <div className="workflow-version-diff-title">
              <strong>版本对比</strong>
              <span>比较两个历史快照的节点、连线和基础信息。</span>
            </div>
            <div className="workflow-version-diff-controls">
              <label>
                基准版本
                <select value={versionDiffBaseId} onChange={(event) => onVersionDiffBaseChange(event.target.value)}>
                  <option value="">选择版本</option>
                  {orderedVersionOptions.map((version) => (
                    <option key={version.id} value={version.id}>
                      #{version.sequence} {version.is_published ? '已发布' : version.note || version.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                目标版本
                <select value={versionDiffTargetId} onChange={(event) => onVersionDiffTargetChange(event.target.value)}>
                  <option value="">选择版本</option>
                  {orderedVersionOptions.map((version) => (
                    <option key={version.id} value={version.id}>
                      #{version.sequence} {version.is_published ? '已发布' : version.note || version.name}
                    </option>
                  ))}
                </select>
              </label>
              <button type="button" disabled={workflowVersions.length < 2 || hasBusyAction} onClick={onCompareVersions}>
                {busy === 'diff' ? '对比中...' : '开始对比'}
              </button>
            </div>
            {versionDiff && (
              <div className="workflow-version-diff-results">
                <p>
                  #{versionDiff.base_version.sequence} 到 #{versionDiff.target_version.sequence}：
                  新增 {versionDiff.summary.added ?? 0}，删除 {versionDiff.summary.removed ?? 0}，变更{' '}
                  {versionDiff.summary.changed ?? 0}
                </p>
                {versionDiff.changes.length === 0 ? (
                  <span>两个版本内容一致。</span>
                ) : (
                  versionDiff.changes.slice(0, 8).map((change, index) => (
                    <article key={`${change.category}-${change.change}-${change.label}-${index}`}>
                      <strong>
                        {versionDiffChangeLabels[change.change]} · {versionDiffCategoryLabels[change.category]}
                      </strong>
                      <span>{change.label}</span>
                      {change.before && <small>之前：{change.before}</small>}
                      {change.after && <small>之后：{change.after}</small>}
                    </article>
                  ))
                )}
              </div>
            )}
          </div>
          <div className="audit-log-list">
            {auditLogs.length === 0 ? (
              <p>暂无审计记录。</p>
            ) : (
              auditLogs.slice(0, 6).map((log) => (
                <article key={log.id}>
                  <strong>{log.summary}</strong>
                  <span>
                    {log.actor_username} · {new Date(log.created_at).toLocaleString('zh-CN')}
                  </span>
                </article>
              ))
            )}
          </div>
        </>
      )}
    </section>
  )
}
