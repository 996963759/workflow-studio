import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  type Connection,
  type Edge,
  type EdgeChange,
  type Node,
  type NodeChange,
  type NodeProps,
} from '@xyflow/react'
import {
  AlertTriangle,
  Archive,
  Bot,
  Braces,
  ChevronRight,
  CircleDot,
  Copy,
  Code2,
  Download,
  GitBranch,
  ListChecks,
  MessageSquareText,
  Play,
  Plus,
  RotateCcw,
  Save,
  Search,
  Settings2,
  Sparkles,
  TerminalSquare,
  Trash2,
  Upload,
  Workflow,
} from 'lucide-react'
import clsx from 'clsx'
import '@xyflow/react/dist/style.css'
import './App.css'

type NodeKind = 'input' | 'llm' | 'knowledge' | 'tool' | 'condition' | 'output'
type ConditionOperator = 'contains' | 'equals' | 'not_empty'
type FailurePolicy = 'stop' | 'continue' | 'skip_downstream'

type WorkflowNodeData = {
  kind: NodeKind
  label: string
  description: string
  model?: string
  temperature?: number
  maxOutputTokens?: number
  timeoutSeconds?: number
  systemPrompt?: string
  prompt?: string
  query?: string
  topK?: number
  toolName?: string
  toolUrl?: string
  toolMethod?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  toolHeaders?: string
  toolParams?: string
  condition?: string
  conditionVariable?: string
  conditionOperator?: ConditionOperator
  conditionValue?: string
  sampleInput?: string
  outputKey?: string
  failurePolicy?: FailurePolicy
  retryCount?: number
  issueLevel?: 'error' | 'warning'
}

type WorkflowNode = Node<WorkflowNodeData, 'workflow'>

type RunStep = {
  nodeId: string
  title: string
  status: 'done' | 'routed' | 'waiting' | 'skipped' | 'error'
  input: string
  output: string
  variable?: string
  provider?: string
  error?: string
}

type WorkflowDefinition = {
  id?: string
  name: string
  version: string
  nodes: WorkflowNode[]
  edges: Edge[]
  updatedAt?: string
}

type WorkflowRecord = Required<Pick<WorkflowDefinition, 'id' | 'name' | 'version' | 'nodes' | 'edges'>> & {
  archived?: boolean
  updatedAt: string
  serverId?: string
  syncedAt?: string
}

type WorkflowSortMode = 'updated' | 'name' | 'sync'
type RunHistoryStatusFilter = 'all' | 'ok' | 'error'

type ServerWorkflowRecord = {
  id: string
  name: string
  version: string
  nodes: WorkflowNode[]
  edges: Edge[]
  updated_at: string
}

type ServerRunRecord = {
  id: string
  workflow_id: string | null
  workflow_name: string
  input_text: string
  status: string
  steps: RunStep[]
  created_at: string
}

type WorkflowStore = {
  activeWorkflowId: string
  workflows: WorkflowRecord[]
}

type WorkflowIssue = {
  id: string
  level: 'error' | 'warning'
  message: string
  nodeId?: string
}

type FieldIssue = {
  field: keyof WorkflowNodeData
  level: 'error' | 'warning'
  message: string
}

type ServerWorkflowIssue = {
  id: string
  level: 'error' | 'warning'
  message: string
  node_id?: string | null
}

type WorkflowValidationResult = {
  errors: ServerWorkflowIssue[]
  warnings: ServerWorkflowIssue[]
  valid: boolean
}

type RemoteValidationState = {
  issues: WorkflowIssue[]
  key: string
  status: 'checking' | 'backend' | 'local'
}

type ProviderStatus = {
  deepseek_configured: boolean
  deepseek_model: string
  deepseek_base_url: string
  openai_configured: boolean
  openai_default_model: string
}

type KnowledgeStatus = {
  directory: string
  document_count: number
  chunk_count: number
}

type WorkflowTemplate = {
  id: string
  name: string
  description: string
  input: string
  nodes: WorkflowNode[]
  edges: Edge[]
}

const LEGACY_STORAGE_KEY = 'workflow-studio.current-workflow'
const WORKFLOWS_STORAGE_KEY = 'workflow-studio.workflows'
const ACTIVE_WORKFLOW_STORAGE_KEY = 'workflow-studio.active-workflow-id'
const API_BASE_URL = 'http://127.0.0.1:8000'

const nodeMeta: Record<
  NodeKind,
  {
    title: string
    icon: typeof CircleDot
    description: string
    color: string
    defaults: Omit<WorkflowNodeData, 'kind'>
  }
> = {
  input: {
    title: '用户输入',
    icon: MessageSquareText,
    description: '收集用户变量',
    color: '#0f766e',
    defaults: {
      label: '用户输入',
      description: '收集主题、受众和输出格式要求。',
      sampleInput: '总结用户反馈，并生成按优先级排序的产品行动项。',
      outputKey: 'user_request',
    },
  },
  llm: {
    title: '大模型',
    icon: Bot,
    description: '生成或改写文本',
    color: '#b45309',
    defaults: {
      label: '大模型草稿',
      description: '调用模型生成结构化回答草稿。',
      model: 'gpt-5.4-mini',
      temperature: 0.4,
      maxOutputTokens: 1200,
      timeoutSeconds: 45,
      systemPrompt: '你是严谨的 AI 工作流助手，回答要结构清晰、可执行。',
      prompt: '根据 {{user_request}} 和检索到的上下文，生成一份简洁回答。',
      outputKey: 'draft',
    },
  },
  knowledge: {
    title: '知识检索',
    icon: Search,
    description: '检索上下文',
    color: '#2563eb',
    defaults: {
      label: '知识库检索',
      description: '搜索已上传文档或已连接知识库。',
      query: '{{user_request}}',
      topK: 4,
      outputKey: 'context',
    },
  },
  tool: {
    title: '工具调用',
    icon: TerminalSquare,
    description: '调用外部动作',
    color: '#7c3aed',
    defaults: {
      label: '工具调用',
      description: '调用连接器、API、脚本或内部动作。',
      toolName: '本地接口调用',
      toolUrl: 'http://127.0.0.1:8000/api/health',
      toolMethod: 'GET',
      toolHeaders: '{\n  "Content-Type": "application/json"\n}',
      toolParams: '{\n  "query": "{{user_request}}"\n}',
      outputKey: 'tool_result',
      failurePolicy: 'continue',
      retryCount: 0,
    },
  },
  condition: {
    title: '条件分支',
    icon: GitBranch,
    description: '按规则路由',
    color: '#be123c',
    defaults: {
      label: '质量判断',
      description: '根据置信度、意图或内容决定下一步。',
      condition: '{{draft}} 包含引用来源',
      conditionVariable: 'draft',
      conditionOperator: 'contains',
      conditionValue: '引用来源',
    },
  },
  output: {
    title: '最终回答',
    icon: Upload,
    description: '返回最终结果',
    color: '#334155',
    defaults: {
      label: '最终回答',
      description: '把变量整理成最终返回给用户的内容。',
      prompt: '{{draft}}\n\n来源：{{context}}',
      outputKey: 'answer',
    },
  },
}

const initialNodes: WorkflowNode[] = [
  {
    id: 'input-1',
    type: 'workflow',
    position: { x: 40, y: 180 },
    data: { kind: 'input', ...nodeMeta.input.defaults },
  },
  {
    id: 'knowledge-1',
    type: 'workflow',
    position: { x: 340, y: 70 },
    data: { kind: 'knowledge', ...nodeMeta.knowledge.defaults },
  },
  {
    id: 'llm-1',
    type: 'workflow',
    position: { x: 660, y: 180 },
    data: { kind: 'llm', ...nodeMeta.llm.defaults },
  },
  {
    id: 'condition-1',
    type: 'workflow',
    position: { x: 970, y: 180 },
    data: { kind: 'condition', ...nodeMeta.condition.defaults },
  },
  {
    id: 'output-1',
    type: 'workflow',
    position: { x: 1280, y: 180 },
    data: { kind: 'output', ...nodeMeta.output.defaults },
  },
]

const initialEdges: Edge[] = [
  { id: 'e-input-knowledge', source: 'input-1', target: 'knowledge-1', animated: true },
  { id: 'e-input-llm', source: 'input-1', target: 'llm-1' },
  { id: 'e-knowledge-llm', source: 'knowledge-1', target: 'llm-1' },
  { id: 'e-llm-condition', source: 'llm-1', target: 'condition-1' },
  { id: 'e-condition-output', source: 'condition-1', target: 'output-1' },
]

const workflowTemplates: WorkflowTemplate[] = [
  {
    id: 'support-rag',
    name: '客服知识库问答',
    description: '检索本地知识库，生成带依据的客服回复。',
    input: '退款多久到账？',
    nodes: initialNodes,
    edges: initialEdges,
  },
  {
    id: 'http-tool',
    name: 'HTTP 工具调用',
    description: '调用本机健康检查接口，并把响应整理为最终输出。',
    input: '检查后端服务是否在线。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 170 },
        data: { kind: 'input', ...nodeMeta.input.defaults, sampleInput: '检查后端服务是否在线。' },
      },
      {
        id: 'tool-1',
        type: 'workflow',
        position: { x: 380, y: 170 },
        data: { kind: 'tool', ...nodeMeta.tool.defaults, label: '后端健康检查', outputKey: 'health_result' },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 720, y: 170 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          prompt: '健康检查结果：\n{{health_result}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-tool', source: 'input-1', target: 'tool-1', animated: true },
      { id: 'e-tool-output', source: 'tool-1', target: 'output-1' },
    ],
  },
  {
    id: 'branch-review',
    name: '条件分支审核',
    description: '根据用户输入是否包含退款，路由到不同回复路径。',
    input: '我要申请退款，订单用了两天。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 180 },
        data: { kind: 'input', ...nodeMeta.input.defaults, sampleInput: '我要申请退款，订单用了两天。' },
      },
      {
        id: 'condition-1',
        type: 'workflow',
        position: { x: 380, y: 180 },
        data: {
          kind: 'condition',
          ...nodeMeta.condition.defaults,
          label: '是否退款诉求',
          conditionVariable: 'user_request',
          conditionOperator: 'contains',
          conditionValue: '退款',
        },
      },
      {
        id: 'refund-output',
        type: 'workflow',
        position: { x: 740, y: 80 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '退款回复',
          prompt: '用户是退款诉求，请按退款规则回复：{{user_request}}',
          outputKey: 'refund_answer',
        },
      },
      {
        id: 'normal-output',
        type: 'workflow',
        position: { x: 740, y: 290 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '普通回复',
          prompt: '用户不是退款诉求，请转入普通客服流程：{{user_request}}',
          outputKey: 'normal_answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-condition', source: 'input-1', target: 'condition-1', animated: true },
      { id: 'e-true', source: 'condition-1', sourceHandle: 'true', target: 'refund-output' },
      { id: 'e-false', source: 'condition-1', sourceHandle: 'false', target: 'normal-output' },
    ],
  },
  {
    id: 'failure-retry',
    name: '失败重试处理',
    description: '演示工具失败后重试，并跳过下游节点。',
    input: '演示失败重试。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 180 },
        data: { kind: 'input', ...nodeMeta.input.defaults, sampleInput: '演示失败重试。' },
      },
      {
        id: 'tool-1',
        type: 'workflow',
        position: { x: 380, y: 180 },
        data: {
          kind: 'tool',
          ...nodeMeta.tool.defaults,
          label: '故障接口调用',
          toolName: 'local.missing',
          toolUrl: 'http://127.0.0.1:8000/api/missing-endpoint',
          toolMethod: 'GET',
          toolHeaders: '{}',
          toolParams: '{}',
          failurePolicy: 'skip_downstream',
          retryCount: 1,
          outputKey: 'tool_result',
        },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 720, y: 180 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          prompt: '如果工具成功，会输出：{{tool_result}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-tool', source: 'input-1', target: 'tool-1', animated: true },
      { id: 'e-tool-output', source: 'tool-1', target: 'output-1' },
    ],
  },
]

const examples = [
  '总结用户反馈，并生成按优先级排序的产品行动项。',
  '根据 CRM 数据和品牌语气，撰写一封新用户欢迎邮件。',
  '检查客服工单，判断紧急程度，并起草回复。',
]

const createWorkflowDefinition = (
  nodes: WorkflowNode[],
  edges: Edge[],
  updatedAt?: string,
  name = '工作流编辑器演示',
): WorkflowDefinition => ({
  name,
  version: '0.2.0',
  nodes,
  edges,
  updatedAt,
})

const createWorkflowRecord = (name = '工作流编辑器演示'): WorkflowRecord => ({
  id: crypto.randomUUID(),
  name,
  version: '0.2.0',
  nodes: structuredClone(initialNodes) as WorkflowNode[],
  edges: structuredClone(initialEdges) as Edge[],
  updatedAt: new Date().toISOString(),
})

const isWorkflowDefinition = (value: unknown): value is WorkflowDefinition => {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<WorkflowDefinition>
  return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges)
}

const serverToWorkflowRecord = (workflow: ServerWorkflowRecord): WorkflowRecord => ({
  id: crypto.randomUUID(),
  archived: false,
  serverId: workflow.id,
  name: workflow.name,
  version: workflow.version || '0.2.0',
  nodes: workflow.nodes,
  edges: workflow.edges,
  updatedAt: workflow.updated_at,
  syncedAt: new Date().toISOString(),
})

const workflowToServerPayload = (workflow: WorkflowRecord) => ({
  name: workflow.name,
  version: workflow.version,
  nodes: workflow.nodes,
  edges: workflow.edges,
})

const createValidationKey = (workflow: WorkflowRecord) =>
  JSON.stringify(workflowToServerPayload(workflow))

const serverIssueToWorkflowIssue = (issue: ServerWorkflowIssue): WorkflowIssue => ({
  id: issue.id,
  level: issue.level,
  message: issue.message,
  nodeId: issue.node_id ?? undefined,
})

const readValidationError = async (response: Response) => {
  try {
    const body = (await response.json()) as { detail?: WorkflowValidationResult }
    return body.detail
  } catch {
    return undefined
  }
}

const loadStoredWorkflow = (): WorkflowDefinition | null => {
  try {
    const raw = window.localStorage.getItem(LEGACY_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    return isWorkflowDefinition(parsed) ? parsed : null
  } catch {
    return null
  }
}

const loadWorkflowStore = (): WorkflowStore => {
  try {
    const raw = window.localStorage.getItem(WORKFLOWS_STORAGE_KEY)
    const activeWorkflowId = window.localStorage.getItem(ACTIVE_WORKFLOW_STORAGE_KEY)
    const parsed = raw ? (JSON.parse(raw) as unknown) : null
    if (
      parsed &&
      typeof parsed === 'object' &&
      Array.isArray((parsed as { workflows?: unknown }).workflows)
    ) {
      const workflows = (parsed as { workflows: WorkflowRecord[] }).workflows.filter(isWorkflowDefinition).map(
        (workflow) => ({
          id: workflow.id ?? crypto.randomUUID(),
          archived: workflow.archived ?? false,
          serverId: workflow.serverId,
          name: workflow.name || '未命名工作流',
          version: workflow.version || '0.2.0',
          nodes: workflow.nodes,
          edges: workflow.edges,
          updatedAt: workflow.updatedAt ?? new Date().toISOString(),
          syncedAt: workflow.syncedAt,
        }),
      )
      if (workflows.length > 0) {
        return {
          activeWorkflowId:
            activeWorkflowId && workflows.some((workflow) => workflow.id === activeWorkflowId)
              ? activeWorkflowId
              : workflows[0].id,
          workflows,
        }
      }
    }
  } catch {
    // Fall through to legacy migration/default creation.
  }

  const legacy = loadStoredWorkflow()
  if (legacy) {
    const migrated: WorkflowRecord = {
      id: crypto.randomUUID(),
      archived: false,
      name: legacy.name || '迁移的工作流',
      version: legacy.version || '0.2.0',
      nodes: legacy.nodes,
      edges: legacy.edges,
      updatedAt: legacy.updatedAt ?? new Date().toISOString(),
    }
    return { activeWorkflowId: migrated.id, workflows: [migrated] }
  }

  const initial = createWorkflowRecord()
  return { activeWorkflowId: initial.id, workflows: [initial] }
}

const persistWorkflowStore = (store: WorkflowStore) => {
  window.localStorage.setItem(WORKFLOWS_STORAGE_KEY, JSON.stringify({ workflows: store.workflows }))
  window.localStorage.setItem(ACTIVE_WORKFLOW_STORAGE_KEY, store.activeWorkflowId)
}

const cloneNodes = (nodes: WorkflowNode[]) => structuredClone(nodes) as WorkflowNode[]
const cloneEdges = (edges: Edge[]) => structuredClone(edges) as Edge[]

const createWorkflowFromTemplate = (template: WorkflowTemplate): WorkflowRecord => ({
  id: crypto.randomUUID(),
  archived: false,
  name: template.name,
  version: '0.2.0',
  nodes: cloneNodes(template.nodes),
  edges: cloneEdges(template.edges),
  updatedAt: new Date().toISOString(),
})

const renderTemplate = (template: string | undefined, context: Record<string, string>) =>
  (template ?? '').replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key: string) => context[key] ?? '')

const getContextValue = (key: string | undefined, context: Record<string, string>) => {
  if (!key) return ''
  const normalized = key.replace(/^\{\{\s*|\s*\}\}$/g, '').trim()
  return context[normalized] ?? ''
}

const createExecutionOrder = (nodes: WorkflowNode[], edges: Edge[]) => {
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const indegree = new Map(nodes.map((node) => [node.id, 0]))
  const outgoing = new Map<string, Edge[]>()

  edges.forEach((edge) => {
    if (!nodeById.has(edge.source) || !nodeById.has(edge.target)) return
    indegree.set(edge.target, (indegree.get(edge.target) ?? 0) + 1)
    outgoing.set(edge.source, [...(outgoing.get(edge.source) ?? []), edge])
  })

  const queue = nodes
    .filter((node) => (indegree.get(node.id) ?? 0) === 0)
    .sort((a, b) => a.position.x - b.position.x)
  const order: WorkflowNode[] = []

  while (queue.length > 0) {
    const node = queue.shift()
    if (!node) continue
    order.push(node)

    ;(outgoing.get(node.id) ?? []).forEach((edge) => {
      const nextDegree = (indegree.get(edge.target) ?? 0) - 1
      indegree.set(edge.target, nextDegree)
      if (nextDegree === 0) {
        const target = nodeById.get(edge.target)
        if (target) {
          queue.push(target)
          queue.sort((a, b) => a.position.x - b.position.x)
        }
      }
    })
  }

  return order.length === nodes.length ? order : null
}

const evaluateCondition = (rule: string | undefined, context: Record<string, string>) => {
  const rendered = renderTemplate(rule, context).trim()
  if (!rendered) return { passed: true, detail: '没有配置判断规则，默认通过。' }

  const containsMatch = rendered.match(/(.+?)\s*(包含|contains)\s*(.+)/i)
  if (containsMatch) {
    const haystack = containsMatch[1].trim()
    const needle = containsMatch[3].trim().replace(/^["'“”‘’]+|["'“”‘’]+$/g, '')
    return {
      passed: needle.length === 0 ? true : haystack.includes(needle),
      detail: `判断 "${haystack}" 是否包含 "${needle}"。`,
    }
  }

  return { passed: !['false', '否', '不通过', '0'].includes(rendered), detail: `规则结果：${rendered}` }
}

const evaluateStructuredCondition = (data: WorkflowNodeData, context: Record<string, string>) => {
  if (!data.conditionVariable && !data.conditionOperator) {
    return evaluateCondition(data.condition, context)
  }

  const value = getContextValue(data.conditionVariable, context)
  const target = renderTemplate(data.conditionValue, context).trim()
  const operator = data.conditionOperator ?? 'contains'

  if (operator === 'not_empty') {
    return {
      passed: value.trim().length > 0,
      detail: `判断 {{${data.conditionVariable || '未选择变量'}}} 是否不为空。`,
    }
  }

  if (operator === 'equals') {
    return {
      passed: value === target,
      detail: `判断 {{${data.conditionVariable || '未选择变量'}}} 是否等于 "${target}"。`,
    }
  }

  return {
    passed: target.length === 0 ? true : value.includes(target),
    detail: `判断 {{${data.conditionVariable || '未选择变量'}}} 是否包含 "${target}"。`,
  }
}

const getConditionInputText = (data: WorkflowNodeData, context: Record<string, string>) => {
  if (!data.conditionVariable && !data.conditionOperator) {
    return renderTemplate(data.condition, context) || '未配置判断规则'
  }

  const operatorLabel: Record<ConditionOperator, string> = {
    contains: '包含',
    equals: '等于',
    not_empty: '不为空',
  }
  const operator = data.conditionOperator ?? 'contains'
  return `{{${data.conditionVariable || '未选择变量'}}} ${operatorLabel[operator]} ${
    operator === 'not_empty' ? '' : data.conditionValue || ''
  }`.trim()
}

const getReachableNodeIds = (startIds: string[], edges: Edge[]) => {
  const reachable = new Set<string>()
  const queue = [...startIds]

  while (queue.length > 0) {
    const current = queue.shift()
    if (!current || reachable.has(current)) continue
    reachable.add(current)
    edges
      .filter((edge) => edge.source === current)
      .forEach((edge) => {
        if (!reachable.has(edge.target)) queue.push(edge.target)
      })
  }

  return reachable
}

const validateNodeFields = (node: WorkflowNode): FieldIssue[] => {
  const issues: FieldIssue[] = []
  const { data } = node
  const outputKey = data.outputKey?.trim()

  if (!data.label.trim()) {
    issues.push({ field: 'label', level: 'error', message: '名称不能为空。' })
  }

  if (outputKey && !/^[A-Za-z_][A-Za-z0-9_]*$/.test(outputKey)) {
    issues.push({ field: 'outputKey', level: 'error', message: '输出变量名只能包含字母、数字和下划线，并且不能以数字开头。' })
  }

  if (data.kind === 'llm' && !data.prompt?.trim()) {
    issues.push({ field: 'prompt', level: 'error', message: '大模型节点需要填写用户提示词。' })
  }
  if (data.kind === 'llm') {
    if (data.temperature !== undefined && (Number.isNaN(data.temperature) || data.temperature < 0 || data.temperature > 2)) {
      issues.push({ field: 'temperature', level: 'error', message: '温度需要在 0 到 2 之间。' })
    }
    if (
      data.maxOutputTokens !== undefined &&
      (!Number.isInteger(data.maxOutputTokens) || data.maxOutputTokens < 1 || data.maxOutputTokens > 32000)
    ) {
      issues.push({ field: 'maxOutputTokens', level: 'error', message: '最大输出长度需要在 1 到 32000 之间。' })
    }
    if (
      data.timeoutSeconds !== undefined &&
      (!Number.isInteger(data.timeoutSeconds) || data.timeoutSeconds < 5 || data.timeoutSeconds > 300)
    ) {
      issues.push({ field: 'timeoutSeconds', level: 'error', message: '超时时间需要在 5 到 300 秒之间。' })
    }
  }

  if (data.kind === 'knowledge' && !data.query?.trim()) {
    issues.push({ field: 'query', level: 'warning', message: '建议填写检索语句，否则会使用运行输入兜底。' })
  }

  if (data.kind === 'tool') {
    if (!data.toolName?.trim()) {
      issues.push({ field: 'toolName', level: 'warning', message: '建议填写工具名称，方便识别运行日志。' })
    }
    if (data.toolUrl?.trim()) {
      try {
        const url = new URL(data.toolUrl.trim())
        if (!['http:', 'https:'].includes(url.protocol)) {
          issues.push({ field: 'toolUrl', level: 'error', message: '请求地址只支持 HTTP 或 HTTPS。' })
        }
      } catch {
        issues.push({ field: 'toolUrl', level: 'error', message: '请求地址必须是合法 URL。' })
      }
    }
    if (data.toolHeaders?.trim()) {
      try {
        const parsed = JSON.parse(data.toolHeaders)
        if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
          issues.push({ field: 'toolHeaders', level: 'error', message: '请求头必须是 JSON 对象。' })
        }
      } catch {
        issues.push({ field: 'toolHeaders', level: 'error', message: '请求头必须是合法 JSON。' })
      }
    }
    if (data.toolParams?.trim()) {
      try {
        JSON.parse(data.toolParams)
      } catch {
        issues.push({ field: 'toolParams', level: 'error', message: '请求体必须是合法 JSON。' })
      }
    }
  }

  if (data.failurePolicy && !['stop', 'continue', 'skip_downstream'].includes(data.failurePolicy)) {
    issues.push({ field: 'failurePolicy', level: 'error', message: '失败策略不支持。' })
  }
  if (
    data.retryCount !== undefined &&
    (!Number.isInteger(data.retryCount) || data.retryCount < 0 || data.retryCount > 5)
  ) {
    issues.push({ field: 'retryCount', level: 'error', message: '重试次数需要在 0 到 5 之间。' })
  }

  if (data.kind === 'condition') {
    if (!data.conditionVariable?.trim()) {
      issues.push({ field: 'conditionVariable', level: 'error', message: '条件分支需要选择判断变量。' })
    }
    if (data.conditionOperator !== 'not_empty' && !data.conditionValue?.trim()) {
      issues.push({ field: 'conditionValue', level: 'warning', message: '判断值为空时，包含判断会默认通过。' })
    }
  }

  if (data.kind === 'output' && !data.prompt?.trim()) {
    issues.push({ field: 'prompt', level: 'error', message: '最终回答节点需要填写输出模板。' })
  }

  return issues
}

const validateWorkflow = (nodes: WorkflowNode[], edges: Edge[]) => {
  const issues: WorkflowIssue[] = []
  const nodeById = new Map(nodes.map((node) => [node.id, node]))
  const validEdges = edges.filter((edge) => nodeById.has(edge.source) && nodeById.has(edge.target))
  const incoming = new Map(nodes.map((node) => [node.id, 0]))
  const outgoing = new Map(nodes.map((node) => [node.id, 0]))

  validEdges.forEach((edge) => {
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1)
    outgoing.set(edge.source, (outgoing.get(edge.source) ?? 0) + 1)
  })

  if (!nodes.some((node) => node.data.kind === 'input')) {
    issues.push({ id: 'missing-input', level: 'error', message: '至少需要一个用户输入节点。' })
  }

  if (!nodes.some((node) => node.data.kind === 'output')) {
    issues.push({ id: 'missing-output', level: 'error', message: '至少需要一个最终回答节点。' })
  }

  if (!createExecutionOrder(nodes, validEdges)) {
    issues.push({ id: 'cycle', level: 'error', message: '工作流存在环形依赖，无法按顺序执行。' })
  }

  nodes.forEach((node) => {
    validateNodeFields(node).forEach((issue) => {
      issues.push({
        id: `field-${node.id}-${String(issue.field)}`,
        level: issue.level,
        nodeId: node.id,
        message: `节点「${node.data.label || node.id}」：${issue.message}`,
      })
    })

    const hasIncoming = (incoming.get(node.id) ?? 0) > 0
    const hasOutgoing = (outgoing.get(node.id) ?? 0) > 0
    if (!hasIncoming && !hasOutgoing && nodes.length > 1) {
      issues.push({
        id: `isolated-${node.id}`,
        level: 'warning',
        nodeId: node.id,
        message: `节点「${node.data.label}」没有任何连线。`,
      })
    }

    if (node.data.kind !== 'input' && !hasIncoming) {
      issues.push({
        id: `missing-upstream-${node.id}`,
        level: 'warning',
        nodeId: node.id,
        message: `节点「${node.data.label}」没有上游输入。`,
      })
    }

    if (node.data.kind === 'output' && !hasIncoming) {
      issues.push({
        id: `output-no-upstream-${node.id}`,
        level: 'error',
        nodeId: node.id,
        message: `最终回答节点「${node.data.label}」必须连接上游节点。`,
      })
    }
  })

  const variableOwners = new Map<string, WorkflowNode[]>()
  nodes.forEach((node) => {
    const key = node.data.outputKey?.trim()
    if (!key) return
    variableOwners.set(key, [...(variableOwners.get(key) ?? []), node])
  })

  variableOwners.forEach((owners, key) => {
    if (owners.length < 2) return
    owners.forEach((node) => {
      issues.push({
        id: `duplicate-var-${key}-${node.id}`,
        level: 'error',
        nodeId: node.id,
        message: `输出变量「${key}」被多个节点重复使用。`,
      })
    })
  })

  return issues
}

function WorkflowNodeCard({ data, selected }: NodeProps<WorkflowNode>) {
  const meta = nodeMeta[data.kind]
  const Icon = meta.icon

  return (
    <div className={clsx('workflow-node', selected && 'selected', data.issueLevel)}>
      <Handle type="target" position={Position.Left} />
      <div className="node-head">
        <span className="node-icon" style={{ color: meta.color, backgroundColor: `${meta.color}16` }}>
          <Icon size={17} />
        </span>
        <div>
          <strong>{data.label}</strong>
          <small>{meta.title}</small>
        </div>
        {data.issueLevel && (
          <span className={clsx('node-warning', data.issueLevel)}>
            <AlertTriangle size={14} />
          </span>
        )}
      </div>
      <p>{data.description}</p>
      <div className="node-vars">
        {data.model && <span>{data.model}</span>}
        {data.toolName && <span>{data.toolName}</span>}
        {data.outputKey && <span>{`{{${data.outputKey}}}`}</span>}
      </div>
      {data.kind === 'condition' ? (
        <>
          <span className="branch-label true">真</span>
          <Handle id="true" type="source" position={Position.Right} className="branch-handle true" />
          <span className="branch-label false">假</span>
          <Handle id="false" type="source" position={Position.Right} className="branch-handle false" />
        </>
      ) : (
        <Handle type="source" position={Position.Right} />
      )}
    </div>
  )
}

const nodeTypes = { workflow: WorkflowNodeCard }

function App() {
  const initialStore = useMemo(() => loadWorkflowStore(), [])
  const [workflowStore, setWorkflowStore] = useState<WorkflowStore>(initialStore)
  const [selectedNodeId, setSelectedNodeId] = useState('llm-1')
  const [runSteps, setRunSteps] = useState<RunStep[]>([])
  const [runHistory, setRunHistory] = useState<ServerRunRecord[]>([])
  const [selectedRunId, setSelectedRunId] = useState('')
  const [runInput, setRunInput] = useState(examples[0])
  const [notice, setNotice] = useState('已加载本地工作流列表。')
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'online' | 'offline'>('unknown')
  const [workflowSearch, setWorkflowSearch] = useState('')
  const [workflowSortMode, setWorkflowSortMode] = useState<WorkflowSortMode>('updated')
  const [showArchivedWorkflows, setShowArchivedWorkflows] = useState(false)
  const [runHistorySearch, setRunHistorySearch] = useState('')
  const [runHistoryStatusFilter, setRunHistoryStatusFilter] = useState<RunHistoryStatusFilter>('all')
  const [remoteValidation, setRemoteValidation] = useState<RemoteValidationState | null>(null)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null)
  const [providerStatusCheckedAt, setProviderStatusCheckedAt] = useState('')
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus | null>(null)
  const [lastBackendSyncAt, setLastBackendSyncAt] = useState('')
  const nextNodeId = useRef(1)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const flowInstanceRef = useRef<{ setCenter: (x: number, y: number, options?: { duration?: number; zoom?: number }) => void } | null>(null)

  const activeWorkflow =
    workflowStore.workflows.find((workflow) => workflow.id === workflowStore.activeWorkflowId) ??
    workflowStore.workflows[0]
  const visibleWorkflows = useMemo(() => {
    const keyword = workflowSearch.trim().toLowerCase()
    return workflowStore.workflows
      .filter((workflow) => showArchivedWorkflows || !workflow.archived)
      .filter((workflow) => !keyword || workflow.name.toLowerCase().includes(keyword))
      .toSorted((a, b) => {
        if (workflowSortMode === 'name') return a.name.localeCompare(b.name, 'zh-CN')
        if (workflowSortMode === 'sync') {
          const syncCompare = Number(Boolean(b.serverId)) - Number(Boolean(a.serverId))
          return syncCompare || new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
        }
        return new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
      })
  }, [showArchivedWorkflows, workflowSearch, workflowSortMode, workflowStore.workflows])
  const visibleRunHistory = useMemo(() => {
    const keyword = runHistorySearch.trim().toLowerCase()
    return runHistory.filter((run) => {
      const hasError = run.status === 'error' || run.steps.some((step) => step.status === 'error')
      if (runHistoryStatusFilter === 'ok' && hasError) return false
      if (runHistoryStatusFilter === 'error' && !hasError) return false
      if (!keyword) return true
      return [run.workflow_name, run.input_text, ...run.steps.flatMap((step) => [step.title, step.input, step.output, step.error ?? ''])]
        .join('\n')
        .toLowerCase()
        .includes(keyword)
    })
  }, [runHistory, runHistorySearch, runHistoryStatusFilter])
  const selectedRunRecord = runHistory.find((run) => run.id === selectedRunId)
  const selectedRunErrorCount = selectedRunRecord?.steps.filter((step) => step.status === 'error').length ?? 0
  const selectedRunDoneCount = selectedRunRecord?.steps.filter((step) => step.status === 'done' || step.status === 'routed').length ?? 0
  const selectedRunSkippedCount = selectedRunRecord?.steps.filter((step) => step.status === 'skipped').length ?? 0
  const nodes = activeWorkflow.nodes
  const edges = activeWorkflow.edges
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0]
  const selectedFieldIssues = selectedNode ? validateNodeFields(selectedNode) : []
  const fieldIssuesByName = selectedFieldIssues.reduce(
    (result, issue) => {
      result[issue.field] = [...(result[issue.field] ?? []), issue]
      return result
    },
    {} as Partial<Record<keyof WorkflowNodeData, FieldIssue[]>>,
  )

  const updateActiveWorkflow = (patch: Partial<WorkflowRecord>) => {
    const updatedAt = new Date().toISOString()
    setWorkflowStore((current) => {
      const next = {
        ...current,
        workflows: current.workflows.map((workflow) =>
          workflow.id === current.activeWorkflowId ? { ...workflow, ...patch, updatedAt } : workflow,
        ),
      }
      persistWorkflowStore(next)
      return next
    })
  }

  const updateActiveNodes = (updater: (current: WorkflowNode[]) => WorkflowNode[]) => {
    updateActiveWorkflow({ nodes: updater(nodes) })
  }

  const updateActiveEdges = (updater: (current: Edge[]) => Edge[]) => {
    updateActiveWorkflow({ edges: updater(edges) })
  }

  const variables = useMemo(
    () =>
      nodes
        .map((node) => node.data.outputKey)
        .filter((key): key is string => Boolean(key))
        .map((key) => `{{${key}}}`),
    [nodes],
  )
  const variableKeys = useMemo(
    () =>
      nodes
        .map((node) => node.data.outputKey?.trim())
        .filter((key): key is string => Boolean(key)),
    [nodes],
  )

  const localWorkflowIssues = useMemo(() => validateWorkflow(nodes, edges), [nodes, edges])
  const validationKey = useMemo(() => createValidationKey(activeWorkflow), [activeWorkflow])
  const workflowIssues =
    remoteValidation && remoteValidation.key === validationKey ? remoteValidation.issues : localWorkflowIssues
  const validationSource =
    remoteValidation && remoteValidation.key === validationKey ? remoteValidation.status : 'checking'
  const blockingIssues = workflowIssues.filter((issue) => issue.level === 'error')
  const nodeIssueLevels = useMemo(() => {
    const levels = new Map<string, 'error' | 'warning'>()
    workflowIssues.forEach((issue) => {
      if (!issue.nodeId) return
      const current = levels.get(issue.nodeId)
      if (current === 'error') return
      levels.set(issue.nodeId, issue.level)
    })
    return levels
  }, [workflowIssues])

  const displayedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        data: {
          ...node.data,
          issueLevel: nodeIssueLevels.get(node.id),
        },
      })),
    [nodeIssueLevels, nodes],
  )

  const hasRealModelProvider = Boolean(providerStatus?.deepseek_configured || providerStatus?.openai_configured)
  const activeProviderLabel = providerStatus?.deepseek_configured
    ? `DeepSeek - ${providerStatus.deepseek_model}`
    : providerStatus?.openai_configured
      ? `OpenAI - ${providerStatus.openai_default_model}`
      : '模拟输出'
  const knowledgeStatusLabel = knowledgeStatus
    ? `${knowledgeStatus.document_count} 个文档 / ${knowledgeStatus.chunk_count} 个片段`
    : '未检查'

  useEffect(() => {
    const controller = new AbortController()
    const currentKey = validationKey

    const timer = window.setTimeout(async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/api/workflows/validate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(workflowToServerPayload(activeWorkflow)),
          signal: controller.signal,
        })
        if (!response.ok) throw new Error('validate failed')
        const result = (await response.json()) as WorkflowValidationResult
        const issues = [...result.errors, ...result.warnings].map(serverIssueToWorkflowIssue)
        setRemoteValidation({ issues, key: currentKey, status: 'backend' })
        setBackendStatus('online')
      } catch (error) {
        if (controller.signal.aborted) return
        setRemoteValidation({ issues: localWorkflowIssues, key: currentKey, status: 'local' })
        setBackendStatus('offline')
        if (!(error instanceof TypeError)) return
      }
    }, 350)

    return () => {
      controller.abort()
      window.clearTimeout(timer)
    }
  }, [activeWorkflow, localWorkflowIssues, validationKey])

  const validateActiveWorkflow = async () => {
    const currentKey = validationKey
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(workflowToServerPayload(activeWorkflow)),
      })
      if (!response.ok) throw new Error('validate failed')
      const result = (await response.json()) as WorkflowValidationResult
      const issues = [...result.errors, ...result.warnings].map(serverIssueToWorkflowIssue)
      setRemoteValidation({ issues, key: currentKey, status: 'backend' })
      setBackendStatus('online')
      return issues
    } catch {
      setRemoteValidation({ issues: localWorkflowIssues, key: currentKey, status: 'local' })
      setBackendStatus('offline')
      return localWorkflowIssues
    }
  }

  const showBlockingIssues = (issues: WorkflowIssue[], action: string) => {
    const errors = issues.filter((issue) => issue.level === 'error')
    if (errors.length === 0) return false

    setRunSteps(
      errors.map((issue, index) => ({
        nodeId: issue.nodeId ?? issue.id,
        title: `${index + 1}. ${action}前校验失败`,
        status: 'error',
        input: '当前工作流定义',
        output: issue.message,
      })),
    )
    setSelectedRunId('')
    setNotice(`发现 ${errors.length} 个严重问题，已阻止${action}。`)
    return errors.length > 0
  }

  const copyText = async (label: string, value: string | undefined) => {
    const content = value?.trim()
    if (!content) {
      setNotice(`${label}为空，无法复制。`)
      return
    }

    try {
      await navigator.clipboard.writeText(content)
      setNotice(`已复制${label}。`)
    } catch {
      setNotice('复制失败：当前浏览器不允许访问剪贴板。')
    }
  }

  const copyCurrentRunSummary = () => {
    const selectedRun = selectedRunRecord
    const title = selectedRun
      ? `${selectedRun.workflow_name} · ${new Date(selectedRun.created_at).toLocaleString('zh-CN')}`
      : activeWorkflow.name
    const content = [
      `运行：${title}`,
      `输入：${selectedRun?.input_text ?? runInput}`,
      ...runSteps.map((step, index) =>
        [
          `${index + 1}. ${step.title} [${step.status}]`,
          `输入：${step.input}`,
          `输出：${step.output}`,
          step.variable ? `写入：${step.variable}` : '',
          step.provider ? `来源：${step.provider}` : '',
          step.error ? `错误：${step.error}` : '',
        ]
          .filter(Boolean)
          .join('\n'),
      ),
    ].join('\n\n')

    void copyText('整次运行结果', content)
  }

  const focusIssueNode = (issue: WorkflowIssue) => {
    if (!issue.nodeId) return
    const node = nodes.find((item) => item.id === issue.nodeId)
    if (!node) {
      setNotice('没有找到这个问题关联的节点。')
      return
    }

    setSelectedNodeId(node.id)
    flowInstanceRef.current?.setCenter(node.position.x + 118, node.position.y + 60, {
      duration: 500,
      zoom: 0.95,
    })
    setNotice(`已定位到节点：${node.data.label}`)
  }

  const refreshProviderStatus = async (showNotice = true) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/provider-status`)
      if (!response.ok) throw new Error('provider status failed')
      const status = (await response.json()) as ProviderStatus
      setProviderStatus(status)
      setProviderStatusCheckedAt(new Date().toISOString())
      setBackendStatus('online')
      if (showNotice) {
        const label = status.deepseek_configured
          ? `DeepSeek 已启用，默认模型：${status.deepseek_model}。`
          : status.openai_configured
            ? `OpenAI 已启用，默认模型：${status.openai_default_model}。`
            : '未检测到模型 Key，后端运行会使用模拟输出。'
        setNotice(label)
      }
      return status
    } catch {
      setProviderStatus(null)
      setProviderStatusCheckedAt('')
      setBackendStatus('offline')
      if (showNotice) setNotice('模型状态读取失败：请确认后端在线。')
      return null
    }
  }

  const refreshKnowledgeStatus = async (showNotice = true) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/knowledge/status`)
      if (!response.ok) throw new Error('knowledge status failed')
      const status = (await response.json()) as KnowledgeStatus
      setKnowledgeStatus(status)
      setBackendStatus('online')
      if (showNotice) {
        setNotice(`本地知识库已加载 ${status.document_count} 个文档，${status.chunk_count} 个片段。`)
      }
      return status
    } catch {
      setKnowledgeStatus(null)
      setBackendStatus('offline')
      if (showNotice) setNotice('知识库状态读取失败：请确认后端在线。')
      return null
    }
  }

  const onNodesChange = (changes: NodeChange<WorkflowNode>[]) => {
    updateActiveNodes((current) => applyNodeChanges(changes, current))
    setNotice('')
  }

  const onEdgesChange = (changes: EdgeChange[]) => {
    updateActiveEdges((current) => applyEdgeChanges(changes, current))
    setNotice('')
  }

  const onConnect = (connection: Connection) => {
    updateActiveEdges((current) =>
      addEdge({ ...connection, animated: connection.source === 'input-1' }, current),
    )
    setNotice('')
  }

  const updateSelectedNode = (patch: Partial<WorkflowNodeData>) => {
    updateActiveNodes((current) =>
      current.map((node) =>
        node.id === selectedNode.id ? { ...node, data: { ...node.data, ...patch } } : node,
      ),
    )
    setNotice('')
  }

  const renderFieldIssues = (field: keyof WorkflowNodeData) => {
    const issues = fieldIssuesByName[field] ?? []
    if (issues.length === 0) return null
    return (
      <div className="field-issues">
        {issues.map((issue) => (
          <span key={`${String(field)}-${issue.message}`} className={issue.level}>
            {issue.message}
          </span>
        ))}
      </div>
    )
  }

  const restoreSelectedNodeDefaults = () => {
    updateSelectedNode({ ...nodeMeta[selectedNode.data.kind].defaults })
    setNotice(`已恢复「${selectedNode.data.label}」的默认配置。`)
  }

  const appendToSelectedField = (
    field: 'prompt' | 'systemPrompt' | 'query' | 'toolUrl' | 'toolHeaders' | 'toolParams' | 'conditionValue',
    variable: string,
  ) => {
    const current = selectedNode.data[field] ?? ''
    updateSelectedNode({ [field]: `${current}${current ? ' ' : ''}{{${variable}}}` })
  }

  const addNode = (kind: NodeKind) => {
    const count = nodes.filter((node) => node.data.kind === kind).length + 1
    const id = `${kind}-custom-${nextNodeId.current}`
    nextNodeId.current += 1
    const node: WorkflowNode = {
      id,
      type: 'workflow',
      position: { x: 240 + count * 70, y: 360 + count * 22 },
      data: {
        kind,
        ...nodeMeta[kind].defaults,
        label: `${nodeMeta[kind].title} ${count}`,
      },
    }

    updateActiveNodes((current) => [...current, node])
    setSelectedNodeId(id)
    setRunSteps([])
    setNotice('')
  }

  const deleteSelectedNode = () => {
    if (!selectedNode || selectedNode.data.kind === 'input') return
    updateActiveNodes((current) => current.filter((node) => node.id !== selectedNode.id))
    updateActiveEdges((current) =>
      current.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id),
    )
    setSelectedNodeId(nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('')
  }

  const checkBackendStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/health`)
      if (!response.ok) throw new Error('health check failed')
      setBackendStatus('online')
      await refreshProviderStatus(false)
      await refreshKnowledgeStatus(false)
      await validateActiveWorkflow()
      setNotice('后端在线，工作流检查已切换到后端校验，知识库状态已刷新。')
    } catch {
      setBackendStatus('offline')
      setNotice('后端离线，当前仍可使用浏览器本地保存。')
    }
  }

  const syncActiveWorkflowToBackend = async () => {
    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '同步')) return

    try {
      const method = activeWorkflow.serverId ? 'PUT' : 'POST'
      const url = activeWorkflow.serverId
        ? `${API_BASE_URL}/api/workflows/${activeWorkflow.serverId}`
        : `${API_BASE_URL}/api/workflows`
      const response = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(workflowToServerPayload(activeWorkflow)),
      })
      if (!response.ok) {
        const validation = await readValidationError(response)
        if (validation) {
          const issues = [...validation.errors, ...validation.warnings].map(serverIssueToWorkflowIssue)
          setRemoteValidation({ issues, key: validationKey, status: 'backend' })
          showBlockingIssues(issues, '同步')
          return
        }
        throw new Error('sync failed')
      }
      const saved = (await response.json()) as ServerWorkflowRecord
      const syncedAt = new Date().toISOString()
      const next = {
        ...workflowStore,
        workflows: workflowStore.workflows.map((workflow) =>
          workflow.id === activeWorkflow.id
            ? {
                ...workflow,
                serverId: saved.id,
                name: saved.name,
                version: saved.version,
                nodes: saved.nodes,
                edges: saved.edges,
                updatedAt: saved.updated_at,
                syncedAt,
              }
            : workflow,
        ),
      }
      setWorkflowStore(next)
      persistWorkflowStore(next)
      setBackendStatus('online')
      setLastBackendSyncAt(syncedAt)
      setNotice('当前工作流已同步到后端。')
    } catch {
      setBackendStatus('offline')
      setNotice('同步失败：后端不可用或请求失败。')
    }
  }

  const loadWorkflowsFromBackend = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows`)
      if (!response.ok) throw new Error('load failed')
      const serverWorkflows = (await response.json()) as ServerWorkflowRecord[]
      const imported = serverWorkflows.map(serverToWorkflowRecord)
      if (imported.length === 0) {
        setBackendStatus('online')
        setNotice('后端在线，但还没有保存的工作流。')
        return
      }
      const existingServerIds = new Set(workflowStore.workflows.map((workflow) => workflow.serverId).filter(Boolean))
      const merged = [
        ...workflowStore.workflows,
        ...imported.filter((workflow) => !existingServerIds.has(workflow.serverId)),
      ]
      const next = {
        activeWorkflowId: imported[0].id,
        workflows: merged,
      }
      setWorkflowStore(next)
      persistWorkflowStore(next)
      setSelectedNodeId(imported[0].nodes[0]?.id ?? '')
      setRunSteps([])
      const syncedAt = new Date().toISOString()
      setBackendStatus('online')
      setLastBackendSyncAt(syncedAt)
      setNotice(`已从后端加载 ${imported.length} 个工作流。`)
    } catch {
      setBackendStatus('offline')
      setNotice('加载失败：后端不可用或请求失败。')
    }
  }

  const runWorkflowOnBackend = async () => {
    if (!activeWorkflow.serverId) {
      setNotice('请先点击“同步到后端”，再使用后端运行。')
      return
    }

    const status = await refreshProviderStatus(false)
    if (status && !status.deepseek_configured && !status.openai_configured) {
      setNotice('未检测到 DeepSeek 或 OpenAI Key，本次后端运行会使用模拟输出。')
    }

    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '后端运行')) return

    try {
      const response = await fetch(`${API_BASE_URL}/api/workflows/${activeWorkflow.serverId}/runs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_text: runInput }),
      })
      if (!response.ok) {
        const validation = await readValidationError(response)
        if (validation) {
          const issues = [...validation.errors, ...validation.warnings].map(serverIssueToWorkflowIssue)
          setRemoteValidation({ issues, key: validationKey, status: 'backend' })
          showBlockingIssues(issues, '后端运行')
          return
        }
        throw new Error('backend run failed')
      }
      const run = (await response.json()) as ServerRunRecord
      setRunSteps(run.steps)
      setRunHistory((current) => [run, ...current.filter((item) => item.id !== run.id)])
      setSelectedRunId(run.id)
      setBackendStatus('online')
      setNotice('已通过后端运行，并保存到运行历史。')
    } catch {
      setBackendStatus('offline')
      setNotice('后端运行失败：请确认后端在线，且当前工作流已同步。')
    }
  }

  const loadRunHistory = async () => {
    if (!activeWorkflow.serverId) {
      setRunHistory([])
      setSelectedRunId('')
      setNotice('当前工作流还没有同步到后端，暂无可加载的后端历史。')
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/runs?workflow_id=${activeWorkflow.serverId}`)
      if (!response.ok) throw new Error('load runs failed')
      const runs = (await response.json()) as ServerRunRecord[]
      setRunHistory(runs)
      setBackendStatus('online')
      setNotice(`已加载当前工作流的 ${runs.length} 条后端运行历史。`)
    } catch {
      setBackendStatus('offline')
      setNotice('加载运行历史失败：后端不可用或请求失败。')
    }
  }

  const selectRunHistory = async (runId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`)
      if (!response.ok) throw new Error('load run failed')
      const run = (await response.json()) as ServerRunRecord
      setRunSteps(run.steps)
      setRunInput(run.input_text)
      setSelectedRunId(run.id)
      setRunHistory((current) => [run, ...current.filter((item) => item.id !== run.id)])
      setBackendStatus('online')
      setNotice('已载入后端运行历史。')
    } catch {
      setBackendStatus('offline')
      setNotice('载入运行历史失败：后端不可用或记录不存在。')
    }
  }

  const deleteRunHistory = async (runId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/runs/${runId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('delete run failed')
      setRunHistory((current) => current.filter((run) => run.id !== runId))
      if (selectedRunId === runId) {
        setSelectedRunId('')
        setRunSteps([])
      }
      setBackendStatus('online')
      setNotice('已删除这条运行历史。')
    } catch {
      setBackendStatus('offline')
      setNotice('删除运行历史失败：后端不可用或记录不存在。')
    }
  }

  const clearCurrentRunHistory = async () => {
    if (!activeWorkflow.serverId) {
      setRunHistory([])
      setSelectedRunId('')
      setRunSteps([])
      setNotice('当前工作流还没有同步到后端，本地历史视图已清空。')
      return
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/runs?workflow_id=${activeWorkflow.serverId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('clear runs failed')
      setRunHistory([])
      setSelectedRunId('')
      setRunSteps([])
      setBackendStatus('online')
      setNotice('已清空当前工作流的后端运行历史。')
    } catch {
      setBackendStatus('offline')
      setNotice('清空运行历史失败：后端不可用或请求失败。')
    }
  }

  const switchWorkflow = (workflowId: string) => {
    const next = { ...workflowStore, activeWorkflowId: workflowId }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    const nextWorkflow = next.workflows.find((workflow) => workflow.id === workflowId)
    setSelectedNodeId(nextWorkflow?.nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('已切换工作流。')
  }

  const createNewWorkflow = () => {
    const nextWorkflow = createWorkflowRecord(`新工作流 ${workflowStore.workflows.length + 1}`)
    const next = {
      activeWorkflowId: nextWorkflow.id,
      workflows: [...workflowStore.workflows, nextWorkflow],
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(nextWorkflow.nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('已新建工作流。')
  }

  const createWorkflowFromSelectedTemplate = (template: WorkflowTemplate) => {
    const nextWorkflow = {
      ...createWorkflowFromTemplate(template),
      name: `${template.name} ${workflowStore.workflows.length + 1}`,
    }
    const next = {
      activeWorkflowId: nextWorkflow.id,
      workflows: [...workflowStore.workflows, nextWorkflow],
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(nextWorkflow.nodes[0]?.id ?? '')
    setRunInput(template.input)
    setRunSteps([])
    setSelectedRunId('')
    setNotice(`已从模板创建「${template.name}」。`)
  }

  const duplicateWorkflow = () => {
    const duplicated: WorkflowRecord = {
      ...activeWorkflow,
      archived: false,
      id: crypto.randomUUID(),
      name: `${activeWorkflow.name} 副本`,
      nodes: cloneNodes(activeWorkflow.nodes),
      edges: cloneEdges(activeWorkflow.edges),
      updatedAt: new Date().toISOString(),
    }
    const next = {
      activeWorkflowId: duplicated.id,
      workflows: [...workflowStore.workflows, duplicated],
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(duplicated.nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('已复制当前工作流。')
  }

  const deleteWorkflow = () => {
    if (workflowStore.workflows.length === 1) {
      setNotice('至少保留一个工作流，不能删除最后一个。')
      return
    }
    const activeAvailableCount = workflowStore.workflows.filter((workflow) => !workflow.archived).length
    if (!activeWorkflow.archived && activeAvailableCount <= 1) {
      setNotice('至少保留一个未归档工作流，不能删除最后一个可用工作流。')
      return
    }
    const remaining = workflowStore.workflows.filter((workflow) => workflow.id !== activeWorkflow.id)
    const nextActive = remaining.find((workflow) => !workflow.archived) ?? remaining[0]
    const next = {
      activeWorkflowId: nextActive.id,
      workflows: remaining,
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(nextActive.nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('已删除当前工作流。')
  }

  const archiveActiveWorkflow = () => {
    const isArchiving = !activeWorkflow.archived
    const activeAvailableCount = workflowStore.workflows.filter((workflow) => !workflow.archived).length

    if (isArchiving && activeAvailableCount <= 1) {
      setNotice('至少保留一个未归档工作流，不能归档最后一个可用工作流。')
      return
    }

    const updatedAt = new Date().toISOString()
    const nextWorkflows = workflowStore.workflows.map((workflow) =>
      workflow.id === activeWorkflow.id ? { ...workflow, archived: isArchiving, updatedAt } : workflow,
    )
    const toggledWorkflow = nextWorkflows.find((workflow) => workflow.id === activeWorkflow.id)
    const fallbackWorkflow = nextWorkflows.find((workflow) => !workflow.archived) ?? toggledWorkflow ?? nextWorkflows[0]
    const nextActive = isArchiving ? fallbackWorkflow : toggledWorkflow ?? fallbackWorkflow
    const next = {
      activeWorkflowId: nextActive.id,
      workflows: nextWorkflows,
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(nextActive.nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice(isArchiving ? '已归档当前工作流。' : '已恢复当前工作流。')
  }

  const runWorkflow = async () => {
    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '运行')) return

    const order = createExecutionOrder(nodes, edges)
    if (!order) {
      setRunSteps([
        {
          nodeId: 'workflow-error',
          title: '执行失败',
          status: 'error',
          input: '当前画布',
          output: '工作流存在环形依赖或无效连线，无法计算执行顺序。',
        },
      ])
      setSelectedRunId('')
      return
    }

    const context: Record<string, string> = {}
    const steps: RunStep[] = []
    let branchOpen = true
    const skippedByBranch = new Set<string>()

    order.forEach((node, index) => {
      if (skippedByBranch.has(node.id)) {
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${node.data.label}`,
          status: 'skipped',
          input: '条件分支未命中该路径。',
          output: '已跳过该分支节点。',
        })
        return
      }

      if (!branchOpen && node.data.kind !== 'output') {
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${node.data.label}`,
          status: 'skipped',
          input: '上一条件节点未通过。',
          output: '已跳过该节点。',
        })
        return
      }

      const data = node.data
      const writeOutput = (value: string) => {
        if (data.outputKey) {
          context[data.outputKey] = value
        }
        return data.outputKey ? `{{${data.outputKey}}}` : undefined
      }

      if (data.kind === 'input') {
        const output = runInput.trim() || data.sampleInput?.trim() || examples[0]
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: '用户请求',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'knowledge') {
        const query = renderTemplate(data.query, context)
        const output = `围绕「${query || runInput}」检索到 ${data.topK ?? 4} 段相关内容，包含产品反馈、处理策略、常见问题和上下文摘要。`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: query || '未配置检索语句',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'llm') {
        const systemPrompt = renderTemplate(data.systemPrompt, context)
        const prompt = renderTemplate(data.prompt, context)
        const output = `模型 ${data.model ?? '未指定'} 根据系统提示和用户提示生成草稿：${prompt.slice(0, 120)}`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: [systemPrompt, prompt].filter(Boolean).join('\n\n') || '未配置提示词',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'tool') {
        const params = renderTemplate(data.toolParams, context)
        const input = params || JSON.stringify(context, null, 2)
        const output = `${data.toolName ?? '未命名工具'} 返回模拟结果，已读取 ${Object.keys(context).length} 个变量。`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input,
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'condition') {
        const result = evaluateStructuredCondition(data, context)
        branchOpen = result.passed
        const branchEdges = edges.filter(
          (edge) => edge.source === node.id && (edge.sourceHandle === 'true' || edge.sourceHandle === 'false'),
        )
        if (branchEdges.length > 0) {
          const inactiveHandle = result.passed ? 'false' : 'true'
          const inactiveTargets = branchEdges
            .filter((edge) => edge.sourceHandle === inactiveHandle)
            .map((edge) => edge.target)
          getReachableNodeIds(inactiveTargets, edges).forEach((id) => skippedByBranch.add(id))
        }
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: result.passed ? 'routed' : 'skipped',
          input: getConditionInputText(data, context),
          output:
            branchEdges.length > 0
              ? `${result.detail} 已进入${result.passed ? '真' : '假'}分支。`
              : result.passed
                ? `${result.detail} 已继续执行。`
                : `${result.detail} 后续非输出节点将跳过。`,
        })
        return
      }

      const output = renderTemplate(data.prompt, context)
      steps.push({
        nodeId: node.id,
        title: `${index + 1}. ${data.label}`,
        status: 'done',
        input: data.prompt ?? '未配置输出模板',
        output: output || '没有可输出内容。',
        variable: writeOutput(output),
      })
    })

    setRunSteps(steps)
    setSelectedRunId('')
    setNotice(`已按 ${order.length} 个节点的连线顺序完成运行。`)
  }

  const saveWorkflow = () => {
    persistWorkflowStore(workflowStore)
    setNotice('已保存全部本地工作流。')
  }

  const exportWorkflow = () => {
    const payload = JSON.stringify(
      createWorkflowDefinition(nodes, edges, new Date().toISOString(), activeWorkflow.name),
      null,
      2,
    )
    const blob = new Blob([payload], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = 'workflow-studio.json'
    link.click()
    URL.revokeObjectURL(url)
    setNotice('已导出 JSON 文件。')
  }

  const importWorkflow = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return

    const reader = new FileReader()
    reader.onload = () => {
      try {
        const parsed = JSON.parse(String(reader.result)) as unknown
        if (!isWorkflowDefinition(parsed)) {
          setNotice('导入失败：JSON 结构不是有效的工作流定义。')
          return
        }

        const imported: WorkflowRecord = {
          id: crypto.randomUUID(),
          name: parsed.name ? `${parsed.name}（导入）` : '导入的工作流',
          version: parsed.version || '0.2.0',
          nodes: parsed.nodes,
          edges: parsed.edges,
          updatedAt: new Date().toISOString(),
        }
        const next = {
          activeWorkflowId: imported.id,
          workflows: [...workflowStore.workflows, imported],
        }
        setWorkflowStore(next)
        persistWorkflowStore(next)
        setSelectedNodeId(imported.nodes[0]?.id ?? '')
        setRunSteps([])
        setNotice('已导入为新的工作流。')
      } catch {
        setNotice('导入失败：文件不是合法 JSON。')
      } finally {
        event.target.value = ''
      }
    }
    reader.readAsText(file)
  }

  const resetWorkflow = () => {
    updateActiveWorkflow({ nodes: cloneNodes(initialNodes), edges: cloneEdges(initialEdges) })
    setSelectedNodeId('llm-1')
    setRunSteps([])
    setNotice('已重置为示例工作流。')
  }

  return (
    <main className="app-shell">
      <aside className="left-rail">
        <div className="brand">
          <span>
            <Workflow size={21} />
          </span>
          <div>
            <strong>流程工坊</strong>
            <small>工作流编辑器</small>
          </div>
        </div>

        <section className="panel">
          <div className="panel-title">
            <Plus size={16} />
            <span>节点库</span>
          </div>
          <div className="node-library">
            {(Object.keys(nodeMeta) as NodeKind[]).map((kind) => {
              const meta = nodeMeta[kind]
              const Icon = meta.icon
              return (
                <button key={kind} type="button" onClick={() => addNode(kind)}>
                  <Icon size={17} style={{ color: meta.color }} />
                  <span>
                    <strong>{meta.title}</strong>
                    <small>{meta.description}</small>
                  </span>
                  <ChevronRight size={15} />
                </button>
              )
            })}
          </div>
        </section>

        <section className="panel template-panel">
          <div className="panel-title">
            <Sparkles size={16} />
            <span>工作流模板</span>
          </div>
          <div className="template-list">
            {workflowTemplates.map((template) => (
              <button key={template.id} type="button" onClick={() => createWorkflowFromSelectedTemplate(template)}>
                <strong>{template.name}</strong>
                <small>{template.description}</small>
              </button>
            ))}
          </div>
        </section>

        <section className="panel workflow-list-panel">
          <div className="panel-title between">
            <span>
              <Workflow size={16} />
              我的工作流
            </span>
            <button type="button" className="mini-action" onClick={createNewWorkflow}>
              <Plus size={14} />
              新建
            </button>
          </div>
          <div className="workflow-tools">
            <label className="workflow-search">
              <Search size={14} />
              <input
                type="search"
                value={workflowSearch}
                onChange={(event) => setWorkflowSearch(event.target.value)}
                placeholder="搜索工作流"
              />
            </label>
            <select
              value={workflowSortMode}
              aria-label="工作流排序"
              onChange={(event) => setWorkflowSortMode(event.target.value as WorkflowSortMode)}
            >
              <option value="updated">最近更新</option>
              <option value="name">名称</option>
              <option value="sync">同步状态</option>
            </select>
            <label className="archive-toggle">
              <input
                type="checkbox"
                checked={showArchivedWorkflows}
                onChange={(event) => {
                  const checked = event.target.checked
                  setShowArchivedWorkflows(checked)
                  if (!checked && activeWorkflow.archived) {
                    const nextVisibleWorkflow = workflowStore.workflows.find((workflow) => !workflow.archived)
                    if (nextVisibleWorkflow) switchWorkflow(nextVisibleWorkflow.id)
                  }
                }}
              />
              显示归档
            </label>
          </div>
          <div className="workflow-list">
            {visibleWorkflows.length > 0 ? (
              visibleWorkflows.map((workflow) => (
                <button
                  key={workflow.id}
                  type="button"
                  className={clsx(workflow.id === activeWorkflow.id && 'active', workflow.archived && 'archived')}
                  onClick={() => switchWorkflow(workflow.id)}
                >
                  <span>
                    {workflow.name}
                    {workflow.archived && <em>归档</em>}
                  </span>
                  <small>
                    {new Date(workflow.updatedAt).toLocaleString('zh-CN')} · {workflow.serverId ? '已同步' : '仅本地'}
                  </small>
                </button>
              ))
            ) : (
              <p className="workflow-empty">{workflowSearch ? '没有匹配的工作流' : '暂无可显示的工作流'}</p>
            )}
          </div>
          <div className="workflow-actions">
            <button type="button" onClick={duplicateWorkflow}>
              <Copy size={14} />
              复制
            </button>
            <button type="button" onClick={archiveActiveWorkflow}>
              {activeWorkflow.archived ? <RotateCcw size={14} /> : <Archive size={14} />}
              {activeWorkflow.archived ? '恢复' : '归档'}
            </button>
            <button type="button" onClick={deleteWorkflow}>
              <Trash2 size={14} />
              删除
            </button>
          </div>
        </section>

        <section className="panel variable-panel">
          <div className="panel-title">
            <Braces size={16} />
            <span>变量</span>
          </div>
          <div className="variable-list">
            {variables.map((variable) => (
              <code key={variable}>{variable}</code>
            ))}
          </div>
        </section>

        <section className="panel validation-panel">
          <div className="panel-title between">
            <span>
              <AlertTriangle size={16} />
              工作流检查
            </span>
            <small className={clsx('validation-source', validationSource)}>
              {validationSource === 'backend' && '后端校验'}
              {validationSource === 'checking' && '后端校验中'}
              {validationSource === 'local' && '本地校验'}
            </small>
          </div>
          <div className="issue-summary">
            <span className={clsx(blockingIssues.length > 0 ? 'bad' : 'good')}>
              {blockingIssues.length} 个严重问题
            </span>
            <span>{workflowIssues.length - blockingIssues.length} 个提醒</span>
          </div>
          {workflowIssues.length === 0 ? (
            <p className="no-issues">当前工作流可以运行。</p>
          ) : (
            <ul className="issue-list">
              {workflowIssues.map((issue) => (
                <li key={issue.id} className={issue.level}>
                  {issue.nodeId ? (
                    <button type="button" onClick={() => focusIssueNode(issue)}>
                      <strong>{issue.level === 'error' ? '错误' : '提醒'}</strong>
                      <span>{issue.message}</span>
                    </button>
                  ) : (
                    <>
                      <strong>{issue.level === 'error' ? '错误' : '提醒'}</strong>
                      <span>{issue.message}</span>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
        </section>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>AI 工作流编排</p>
            <input
              className="workflow-name-input"
              value={activeWorkflow.name}
              onChange={(event) => updateActiveWorkflow({ name: event.target.value })}
              aria-label="工作流名称"
            />
            <div className="backend-status-row">
              <span className={clsx('backend-dot', backendStatus)} />
              <span>
                后端
                {backendStatus === 'online' && '在线'}
                {backendStatus === 'offline' && '离线'}
                {backendStatus === 'unknown' && '未检查'}
              </span>
              {activeWorkflow.serverId && <span>后端 ID：{activeWorkflow.serverId.slice(0, 8)}</span>}
              {(lastBackendSyncAt || activeWorkflow.syncedAt) && (
                <span>
                  同步：{new Date(lastBackendSyncAt || activeWorkflow.syncedAt || '').toLocaleString('zh-CN')}
                </span>
              )}
            </div>
          </div>
          <div className="toolbar">
            <input
              ref={fileInputRef}
              type="file"
              accept="application/json,.json"
              className="file-input"
              onChange={importWorkflow}
            />
            <button type="button" className="ghost" onClick={() => fileInputRef.current?.click()}>
              <Upload size={17} />
              导入
            </button>
            <button type="button" className="ghost" onClick={exportWorkflow}>
              <Download size={17} />
              导出
            </button>
            <button type="button" className="ghost" onClick={resetWorkflow}>
              <Trash2 size={17} />
              重置
            </button>
            <button type="button" className="ghost" onClick={saveWorkflow}>
              <Save size={17} />
              保存
            </button>
            <button type="button" className="ghost" onClick={checkBackendStatus}>
              检查后端
            </button>
            <button type="button" className="ghost" onClick={syncActiveWorkflowToBackend}>
              同步到后端
            </button>
            <button type="button" className="ghost" onClick={loadWorkflowsFromBackend}>
              从后端加载
            </button>
            <button type="button" className="primary" onClick={runWorkflow}>
              <Play size={17} />
              运行
            </button>
          </div>
        </header>

        <div className="canvas-wrap">
          {notice && (
            <div className="workspace-notice">
              <span>{notice}</span>
              <time>当前工作流：{activeWorkflow.name}</time>
            </div>
          )}
          <ReactFlow
            nodes={displayedNodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
            onInit={(instance) => {
              flowInstanceRef.current = instance
            }}
            fitView
            minZoom={0.35}
            maxZoom={1.4}
          >
            <Background color="#cbd5e1" gap={22} size={1} />
            <MiniMap pannable zoomable nodeStrokeWidth={3} />
            <Controls />
          </ReactFlow>
        </div>
      </section>

      <aside className="right-rail">
        <section className="panel inspector">
          <div className="panel-title between">
            <span>
              <Settings2 size={16} />
              节点配置
            </span>
            <button type="button" className="icon-button" onClick={deleteSelectedNode}>
              <Trash2 size={16} />
            </button>
          </div>
          <button type="button" className="restore-defaults-button" onClick={restoreSelectedNodeDefaults}>
            恢复默认配置
          </button>

          <label>
            名称
            <input
              value={selectedNode.data.label}
              onChange={(event) => updateSelectedNode({ label: event.target.value })}
            />
            {renderFieldIssues('label')}
          </label>
          <label>
            用途说明
            <textarea
              value={selectedNode.data.description}
              onChange={(event) => updateSelectedNode({ description: event.target.value })}
            />
          </label>

          {selectedNode.data.kind === 'llm' && (
            <>
              <label>
                模型
                <select
                  value={selectedNode.data.model}
                  onChange={(event) => updateSelectedNode({ model: event.target.value })}
                >
                  <option>deepseek-v4-flash</option>
                  <option>deepseek-v4-pro</option>
                  <option>gpt-5.4-mini</option>
                  <option>gpt-5.4</option>
                  <option>gpt-5.3-codex</option>
                </select>
              </label>
              <div className="llm-params-grid">
                <label>
                  温度
                  <input
                    min={0}
                    max={2}
                    step={0.1}
                    type="number"
                    value={selectedNode.data.temperature ?? 0.4}
                    onChange={(event) => updateSelectedNode({ temperature: Number(event.target.value) })}
                  />
                  {renderFieldIssues('temperature')}
                </label>
                <label>
                  最大输出
                  <input
                    min={1}
                    max={32000}
                    step={100}
                    type="number"
                    value={selectedNode.data.maxOutputTokens ?? 1200}
                    onChange={(event) => updateSelectedNode({ maxOutputTokens: Number(event.target.value) })}
                  />
                  {renderFieldIssues('maxOutputTokens')}
                </label>
                <label>
                  超时秒数
                  <input
                    min={5}
                    max={300}
                    step={5}
                    type="number"
                    value={selectedNode.data.timeoutSeconds ?? 45}
                    onChange={(event) => updateSelectedNode({ timeoutSeconds: Number(event.target.value) })}
                  />
                  {renderFieldIssues('timeoutSeconds')}
                </label>
              </div>
              <label>
                系统提示词
                <textarea
                  rows={4}
                  value={selectedNode.data.systemPrompt ?? ''}
                  onChange={(event) => updateSelectedNode({ systemPrompt: event.target.value })}
                />
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('systemPrompt', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
              <label>
                用户提示词
                <textarea
                  rows={6}
                  value={selectedNode.data.prompt}
                  onChange={(event) => updateSelectedNode({ prompt: event.target.value })}
                />
                {renderFieldIssues('prompt')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('prompt', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'knowledge' && (
            <>
              <label>
                检索语句
                <input
                  value={selectedNode.data.query}
                  onChange={(event) => updateSelectedNode({ query: event.target.value })}
                />
                {renderFieldIssues('query')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('query', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
              <label>
                返回条数
                <input
                  min={1}
                  max={10}
                  type="number"
                  value={selectedNode.data.topK ?? 4}
                  onChange={(event) => updateSelectedNode({ topK: Number(event.target.value) })}
                />
              </label>
            </>
          )}

          {selectedNode.data.kind === 'tool' && (
            <>
              <label>
                工具名称
                <input
                  value={selectedNode.data.toolName}
                  onChange={(event) => updateSelectedNode({ toolName: event.target.value })}
                />
                {renderFieldIssues('toolName')}
              </label>
              <label>
                请求地址
                <input
                  value={selectedNode.data.toolUrl ?? ''}
                  placeholder="http://127.0.0.1:8000/api/health"
                  onChange={(event) => updateSelectedNode({ toolUrl: event.target.value })}
                />
                {renderFieldIssues('toolUrl')}
              </label>
              <label>
                请求方法
                <select
                  value={selectedNode.data.toolMethod ?? 'GET'}
                  onChange={(event) => updateSelectedNode({ toolMethod: event.target.value as WorkflowNodeData['toolMethod'] })}
                >
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="PATCH">PATCH</option>
                  <option value="DELETE">DELETE</option>
                </select>
              </label>
              <label>
                请求头 JSON
                <textarea
                  rows={4}
                  value={selectedNode.data.toolHeaders ?? ''}
                  onChange={(event) => updateSelectedNode({ toolHeaders: event.target.value })}
                />
                {renderFieldIssues('toolHeaders')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('toolHeaders', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
              <label>
                请求体 JSON
                <textarea
                  rows={5}
                  value={selectedNode.data.toolParams ?? ''}
                  onChange={(event) => updateSelectedNode({ toolParams: event.target.value })}
                />
                {renderFieldIssues('toolParams')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('toolParams', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'condition' && (
            <div className="condition-form">
              <label>
                判断变量
                <select
                  value={selectedNode.data.conditionVariable ?? ''}
                  onChange={(event) => updateSelectedNode({ conditionVariable: event.target.value })}
                >
                  <option value="">选择变量</option>
                  {variableKeys.map((variable) => (
                    <option key={variable} value={variable}>
                      {`{{${variable}}}`}
                    </option>
                  ))}
                </select>
                {renderFieldIssues('conditionVariable')}
              </label>
              <label>
                判断方式
                <select
                  value={selectedNode.data.conditionOperator ?? 'contains'}
                  onChange={(event) =>
                    updateSelectedNode({ conditionOperator: event.target.value as ConditionOperator })
                  }
                >
                  <option value="contains">包含</option>
                  <option value="equals">等于</option>
                  <option value="not_empty">不为空</option>
                </select>
              </label>
              {selectedNode.data.conditionOperator !== 'not_empty' && (
                <>
                  <label>
                    判断值
                    <input
                      value={selectedNode.data.conditionValue ?? ''}
                      onChange={(event) => updateSelectedNode({ conditionValue: event.target.value })}
                    />
                    {renderFieldIssues('conditionValue')}
                  </label>
                  <div className="insert-row">
                    {variableKeys.map((variable) => (
                      <button
                        key={variable}
                        type="button"
                        onClick={() => appendToSelectedField('conditionValue', variable)}
                      >
                        {`{{${variable}}}`}
                      </button>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {selectedNode.data.kind === 'input' && (
            <label>
              示例输入
              <textarea
                rows={4}
                value={selectedNode.data.sampleInput ?? ''}
                onChange={(event) => updateSelectedNode({ sampleInput: event.target.value })}
              />
            </label>
          )}

          {selectedNode.data.kind === 'output' && (
            <>
              <label>
                输出模板
                <textarea
                  rows={6}
                  value={selectedNode.data.prompt ?? ''}
                  onChange={(event) => updateSelectedNode({ prompt: event.target.value })}
                />
                {renderFieldIssues('prompt')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('prompt', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          <label>
            输出变量名
            <input
              value={selectedNode.data.outputKey ?? ''}
              onChange={(event) => updateSelectedNode({ outputKey: event.target.value })}
              placeholder="可选"
            />
            {renderFieldIssues('outputKey')}
          </label>
          {selectedNode.data.kind !== 'input' && (
            <div className="failure-policy-grid">
              <label>
                失败策略
                <select
                  value={selectedNode.data.failurePolicy ?? 'stop'}
                  onChange={(event) => updateSelectedNode({ failurePolicy: event.target.value as FailurePolicy })}
                >
                  <option value="stop">终止运行</option>
                  <option value="continue">记录错误并继续</option>
                  <option value="skip_downstream">跳过下游节点</option>
                </select>
                {renderFieldIssues('failurePolicy')}
              </label>
              <label>
                重试次数
                <input
                  min={0}
                  max={5}
                  step={1}
                  type="number"
                  value={selectedNode.data.retryCount ?? 0}
                  onChange={(event) => updateSelectedNode({ retryCount: Number(event.target.value) })}
                />
                {renderFieldIssues('retryCount')}
              </label>
            </div>
          )}
        </section>

        <section className="panel model-status-panel">
          <div className="panel-title between">
            <span>
              <Bot size={16} />
              模型状态
            </span>
            <button type="button" className="mini-action" onClick={() => refreshProviderStatus()}>
              刷新
            </button>
          </div>
          <div className="model-status-current">
            <span className={clsx('model-status-dot', hasRealModelProvider ? 'ready' : 'fallback')} />
            <strong>{activeProviderLabel}</strong>
          </div>
          <div className="model-status-grid">
            <div>
              <span>DeepSeek</span>
              <strong className={clsx(providerStatus?.deepseek_configured ? 'ready' : 'fallback')}>
                {providerStatus?.deepseek_configured ? '已配置' : '未配置'}
              </strong>
            </div>
            <div>
              <span>默认模型</span>
              <strong>{providerStatus?.deepseek_model ?? '未读取'}</strong>
            </div>
            <div>
              <span>OpenAI</span>
              <strong className={clsx(providerStatus?.openai_configured ? 'ready' : 'fallback')}>
                {providerStatus?.openai_configured ? '已配置' : '未配置'}
              </strong>
            </div>
            <div>
              <span>后端状态</span>
              <strong>{backendStatus === 'online' ? '在线' : backendStatus === 'offline' ? '离线' : '未检查'}</strong>
            </div>
          </div>
          <p className="model-status-note">
            {hasRealModelProvider ? '后端运行会优先使用真实模型。' : '未配置模型 Key 时，后端运行会自动使用模拟输出。'}
          </p>
          {providerStatusCheckedAt && (
            <time className="model-status-time">
              更新：{new Date(providerStatusCheckedAt).toLocaleString('zh-CN')}
            </time>
          )}
        </section>

        <section className="panel knowledge-status-panel">
          <div className="panel-title between">
            <span>
              <Search size={16} />
              知识库
            </span>
            <button type="button" className="mini-action" onClick={() => refreshKnowledgeStatus()}>
              刷新
            </button>
          </div>
          <div className="model-status-current">
            <span className={clsx('model-status-dot', knowledgeStatus?.document_count ? 'ready' : 'fallback')} />
            <strong>{knowledgeStatusLabel}</strong>
          </div>
          <p className="model-status-note">
            知识检索节点会读取后端本地 knowledge 目录中的 Markdown 和 TXT 文档。
          </p>
          {knowledgeStatus && <time className="model-status-time">{knowledgeStatus.directory}</time>}
        </section>

        <section className="panel runner">
          <div className="panel-title">
            <ListChecks size={16} />
            <span>运行预览</span>
          </div>
          <div className="example-picker">
            {examples.map((example) => (
              <button
                type="button"
                className={clsx(runInput === example && 'active')}
                key={example}
                onClick={() => setRunInput(example)}
              >
                {example}
              </button>
            ))}
          </div>
          <label className="run-input">
            本次运行输入
            <textarea
              rows={4}
              value={runInput}
              onChange={(event) => setRunInput(event.target.value)}
            />
          </label>
          <div className="runner-actions">
            <button type="button" onClick={runWorkflowOnBackend}>
              后端运行
            </button>
            <button type="button" onClick={loadRunHistory}>
              加载历史
            </button>
            <button type="button" onClick={clearCurrentRunHistory}>
              清空历史
            </button>
          </div>

          <div className="run-history-tools">
            <label className="run-history-search">
              <Search size={14} />
              <input
                type="search"
                value={runHistorySearch}
                onChange={(event) => setRunHistorySearch(event.target.value)}
                placeholder="搜索输入或输出"
              />
            </label>
            <select
              value={runHistoryStatusFilter}
              aria-label="运行历史状态筛选"
              onChange={(event) => setRunHistoryStatusFilter(event.target.value as RunHistoryStatusFilter)}
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
                    <button type="button" onClick={() => selectRunHistory(run.id)}>
                      <strong>{run.workflow_name}</strong>
                      <span>{new Date(run.created_at).toLocaleString('zh-CN')}</span>
                      <small>{run.input_text}</small>
                      <small>{lastStep ? `结果：${lastStep.output}` : '暂无节点输出'}</small>
                    </button>
                    <span className={clsx('run-status-badge', hasError ? 'error' : 'ok')}>
                      {hasError ? '失败' : '成功'}
                    </span>
                    <button
                      type="button"
                      className="run-delete-button"
                      aria-label="删除运行历史"
                      onClick={() => deleteRunHistory(run.id)}
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
                  </div>
                  <button type="button" onClick={copyCurrentRunSummary}>
                    <Copy size={12} />
                    复制整次结果
                  </button>
                </div>
                {runSteps.map((step) => (
                  <article key={step.nodeId}>
                    <span className={clsx('status-dot', step.status)} />
                    <div>
                      <strong>{step.title}</strong>
                      <dl>
                        <div>
                          <dt>
                            输入
                            <button type="button" onClick={() => copyText('节点输入', step.input)}>
                              <Copy size={12} />
                              复制
                            </button>
                          </dt>
                          <dd>{step.input}</dd>
                        </div>
                        <div>
                          <dt>
                            输出
                            <button type="button" onClick={() => copyText('节点输出', step.output)}>
                              <Copy size={12} />
                              复制
                            </button>
                          </dt>
                          <dd>{step.output}</dd>
                        </div>
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
                              <button type="button" onClick={() => copyText('错误原因', step.error)}>
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
                ))}
              </>
            )}
          </div>
        </section>

        <section className="panel json-panel">
          <div className="panel-title">
            <Code2 size={16} />
            <span>定义摘要</span>
          </div>
          <pre>
            {JSON.stringify(
              {
                节点数: nodes.length,
                连线数: edges.length,
                变量数: variables.length,
                严重问题: blockingIssues.length,
                提醒: workflowIssues.length - blockingIssues.length,
              },
              null,
              2,
            )}
          </pre>
        </section>
      </aside>
    </main>
  )
}

export default App
