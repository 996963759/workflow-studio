import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react'
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
  Shield,
  Sparkles,
  TerminalSquare,
  Trash2,
  Upload,
  Workflow,
} from 'lucide-react'
import clsx from 'clsx'
import '@xyflow/react/dist/style.css'
import './App.css'
import { AuthView } from './components/AuthView'

type NodeKind =
  | 'input'
  | 'assign'
  | 'template'
  | 'json'
  | 'code'
  | 'loop'
  | 'aggregate'
  | 'llm'
  | 'knowledge'
  | 'tool'
  | 'tts'
  | 'image'
  | 'condition'
  | 'output'
type ConditionOperator = 'contains' | 'equals' | 'not_empty'
type FailurePolicy = 'stop' | 'continue' | 'skip_downstream'
type KnowledgeProvider = 'local' | 'paismart'

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
  assignmentValue?: string
  templateText?: string
  jsonSource?: string
  jsonPath?: string
  codeExpression?: string
  loopItems?: string
  loopTemplate?: string
  loopSeparator?: string
  aggregateVariables?: string
  aggregateSeparator?: string
  query?: string
  topK?: number
  knowledgeProvider?: KnowledgeProvider
  toolName?: string
  toolUrl?: string
  toolMethod?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'
  toolHeaders?: string
  toolParams?: string
  ttsText?: string
  ttsModel?: string
  ttsVoice?: string
  audioFormat?: 'mp3' | 'wav'
  speechRate?: number
  imagePrompt?: string
  imageModel?: string
  imageSize?: string
  imageCount?: number
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
  nodeId?: string
  node_id?: string
  title: string
  status: 'done' | 'routed' | 'waiting' | 'skipped' | 'error'
  input: string
  output: string
  variable?: string
  provider?: string
  error?: string
  duration_ms?: number
  attempt_count?: number
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
type WorkflowSyncState = 'local' | 'synced' | 'dirty'
type RunHistoryStatusFilter = 'all' | 'ok' | 'error'
type AdminView = 'node' | 'system' | 'team' | 'model' | 'knowledge' | 'ops' | 'json'

type ServerWorkflowRecord = {
  id: string
  name: string
  version: string
  nodes: WorkflowNode[]
  edges: Edge[]
  archived?: boolean
  updated_at: string
}

type WorkflowVersionRecord = {
  id: string
  workflow_id: string
  sequence: number
  name: string
  version: string
  nodes: WorkflowNode[]
  edges: Edge[]
  archived: boolean
  created_by: string
  note?: string | null
  created_at: string
}

type AuditLogRecord = {
  id: string
  workspace_id: string
  actor_user_id: string
  actor_username: string
  action: string
  resource_type: string
  resource_id?: string | null
  summary: string
  metadata: Record<string, unknown>
  created_at: string
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

type AuthUser = {
  id: string
  username: string
  created_at: string
}

type AuthSession = {
  token: string
  user: AuthUser
}

type WorkspaceRecord = {
  id: string
  name: string
  owner_id: string
  role: 'owner' | 'editor' | 'viewer'
  created_at: string
}

type WorkspaceMemberRecord = {
  id: string
  username: string
  role: WorkspaceRecord['role']
  created_at: string
}

type WorkspaceInvitationRecord = {
  id: string
  workspace_id: string
  workspace_name?: string | null
  code: string
  role: 'owner' | 'editor' | 'viewer'
  status: 'pending' | 'accepted' | 'revoked' | 'expired'
  created_by: string
  created_by_username?: string | null
  accepted_by?: string | null
  accepted_by_username?: string | null
  created_at: string
  expires_at: string
  accepted_at?: string | null
  revoked_at?: string | null
}

type RunJobRecord = {
  id: string
  workflow_id: string
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  input_text: string
  run_id?: string | null
  error?: string | null
  created_at: string
  updated_at: string
}

type BackendWorkflowLoadMode = 'manual' | 'startup'

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

type AdminOverviewRecord = {
  status: string
  database: string
  queue_backend: string
  workspace: WorkspaceRecord
  counts: Record<string, number>
  settings: {
    app_env?: string
    session_ttl_hours?: number
    workspace_invitation_ttl_hours?: number
    run_job_workers?: number
    kafka_run_job_topic?: string
    external_rag_enabled?: boolean
    cors_origins?: string[]
    model_config_secret_configured?: boolean
  }
  provider_status: ProviderStatus
  knowledge_status: KnowledgeStatus
  run_metrics: RunMetricsRecord
  recent_audit_logs: AuditLogRecord[]
  recent_run_jobs: RunJobRecord[]
}

type RunMetricsRecord = {
  total_runs: number
  sampled_runs: number
  ok_runs: number
  error_runs: number
  success_rate: number
  average_duration_ms: number
  average_step_count: number
  recent_failed_runs: ServerRunRecord[]
}

type ProviderStatus = {
  deepseek_configured: boolean
  deepseek_model: string
  deepseek_base_url: string
  openai_configured: boolean
  openai_default_model: string
  aliyun_configured?: boolean
  aliyun_tts_model?: string
  aliyun_image_model?: string
  external_rag_enabled?: boolean
  external_rag_provider?: string
  external_rag_base_url?: string
}

type ModelConfigRecord = {
  provider: string
  enabled: boolean
  model: string
  base_url?: string | null
  has_api_key: boolean
  masked_api_key?: string | null
  updated_at?: string | null
}

type ModelConfigFeedback = {
  provider: RuntimeConfigKey
  type: 'ok' | 'error' | 'info'
  text: string
}

type ModelConfigAction = 'load' | 'save' | 'test'
type ProviderConfigKey = 'deepseek' | 'aliyun'
type RuntimeConfigKey = ProviderConfigKey | 'paismart'

type ProviderConfigState = {
  record: ModelConfigRecord | null
  form: {
    enabled: boolean
    model: string
    baseUrl: string
    apiKey: string
  }
}

const PROVIDER_CONFIG_DEFAULTS: Record<ProviderConfigKey, ProviderConfigState['form']> = {
  deepseek: {
    enabled: true,
    model: 'deepseek-v4-flash',
    baseUrl: 'https://api.deepseek.com',
    apiKey: '',
  },
  aliyun: {
    enabled: true,
    model: 'cosyvoice-v2',
    baseUrl: 'https://dashscope.aliyuncs.com',
    apiKey: '',
  },
}

const PAISMART_CONFIG_DEFAULTS: ProviderConfigState['form'] = {
  enabled: true,
  model: 'hybrid',
  baseUrl: 'http://127.0.0.1:8080',
  apiKey: '',
}

const PROVIDER_CONFIG_LABELS: Record<RuntimeConfigKey, string> = {
  deepseek: 'DeepSeek',
  aliyun: '阿里云百炼',
  paismart: 'PaiSmart RAG',
}

const ttsVoiceOptions = [
  { value: 'longxiaochun_v2', label: '龙小淳 V2 - 温暖女声' },
  { value: 'longxiaoxia_v2', label: '龙小夏 V2 - 清亮女声' },
  { value: 'longxiaocheng_v2', label: '龙小诚 V2 - 稳重男声' },
  { value: 'longxiaobai_v2', label: '龙小白 V2 - 自然女声' },
  { value: 'longlaotie_v2', label: '龙老铁 V2 - 亲切男声' },
]

const createDefaultProviderConfigForm = (provider: ProviderConfigKey) => ({ ...PROVIDER_CONFIG_DEFAULTS[provider] })
const createEmptyRunMetrics = (): RunMetricsRecord => ({
  total_runs: 0,
  sampled_runs: 0,
  ok_runs: 0,
  error_runs: 0,
  success_rate: 0,
  average_duration_ms: 0,
  average_step_count: 0,
  recent_failed_runs: [],
})

type KnowledgeStatus = {
  directory: string
  document_count: number
  chunk_count: number
  indexed_chunk_count?: number
}

type KnowledgeDocument = {
  name: string
  size: number
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
const AUTH_STORAGE_KEY = 'workflow-studio.auth-session'
const ACTIVE_WORKSPACE_STORAGE_KEY = 'workflow-studio.active-workspace-id'
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'

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
  assign: {
    title: '变量赋值',
    icon: Braces,
    description: '写入固定或模板变量',
    color: '#0f766e',
    defaults: {
      label: '变量赋值',
      description: '把固定文本或模板渲染结果写入变量，供下游节点使用。',
      assignmentValue: '处理主题：{{user_request}}',
      outputKey: 'assigned_value',
    },
  },
  template: {
    title: '文本模板',
    icon: Braces,
    description: '拼装提示词或文本',
    color: '#64748b',
    defaults: {
      label: '文本模板',
      description: '把多个变量拼装成一段结构化文本。',
      templateText: '用户需求：{{user_request}}\n处理结果：{{draft}}',
      outputKey: 'templated_text',
    },
  },
  json: {
    title: 'JSON 解析',
    icon: Code2,
    description: '从 JSON 中提取字段',
    color: '#0891b2',
    defaults: {
      label: 'JSON 解析',
      description: '解析上游 JSON，并用路径提取字段，例如 items.0.title。',
      jsonSource: '{{draft}}',
      jsonPath: '',
      outputKey: 'json_value',
      failurePolicy: 'continue',
      retryCount: 0,
    },
  },
  code: {
    title: '代码执行',
    icon: TerminalSquare,
    description: '执行受限表达式',
    color: '#7c2d12',
    defaults: {
      label: '代码执行',
      description: '执行受限 Python 表达式，可读取变量并做简单计算或格式化。',
      codeExpression: "upper(user_request)",
      outputKey: 'code_result',
      failurePolicy: 'continue',
      retryCount: 0,
    },
  },
  loop: {
    title: '循环迭代',
    icon: RotateCcw,
    description: '逐项渲染列表',
    color: '#9333ea',
    defaults: {
      label: '循环迭代',
      description: '按行或 JSON 数组遍历输入，每一项用模板渲染后合并。',
      loopItems: '{{json_value}}',
      loopTemplate: '- 第 {{index}} 项：{{item}}',
      loopSeparator: '\n',
      outputKey: 'loop_result',
    },
  },
  aggregate: {
    title: '结果聚合',
    icon: ListChecks,
    description: '合并多个变量',
    color: '#475569',
    defaults: {
      label: '结果聚合',
      description: '按变量名收集上游结果，合并成最终上下文。',
      aggregateVariables: 'draft\nloop_result',
      aggregateSeparator: '\n\n',
      outputKey: 'aggregated_result',
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
      knowledgeProvider: 'local',
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
  tts: {
    title: '文字转语音',
    icon: MessageSquareText,
    description: '阿里云 TTS 合成音频',
    color: '#0e7490',
    defaults: {
      label: '文字转语音',
      description: '调用阿里云百炼 CosyVoice，把文本合成为音频。',
      ttsModel: 'cosyvoice-v2',
      ttsVoice: 'longxiaochun_v2',
      audioFormat: 'mp3',
      speechRate: 1,
      ttsText: '{{draft}}',
      outputKey: 'audio_url',
      failurePolicy: 'continue',
      retryCount: 0,
    },
  },
  image: {
    title: '图片生成',
    icon: Sparkles,
    description: '阿里云图片生成',
    color: '#c2410c',
    defaults: {
      label: '图片生成',
      description: '调用阿里云百炼通义万相，根据提示词生成图片。',
      imageModel: 'wanx2.1-t2i-turbo',
      imagePrompt: '为 {{user_request}} 生成一张干净、专业的配图。',
      imageSize: '1024*1024',
      imageCount: 1,
      outputKey: 'image_urls',
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
    id: 'llm-tts-broadcast',
    name: '文案生成并转语音',
    description: '先让大模型生成适合朗读的短文案，再交给阿里云 TTS 合成音频。',
    input: '给咖啡店新品燕麦拿铁写一段 20 秒中文口播，语气温暖、有购买引导。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 170 },
        data: {
          kind: 'input',
          ...nodeMeta.input.defaults,
          label: '口播需求',
          description: '输入要生成的口播主题、时长、语气和受众。',
          sampleInput: '给咖啡店新品燕麦拿铁写一段 20 秒中文口播，语气温暖、有购买引导。',
          outputKey: 'voice_request',
        },
      },
      {
        id: 'llm-1',
        type: 'workflow',
        position: { x: 380, y: 170 },
        data: {
          kind: 'llm',
          ...nodeMeta.llm.defaults,
          label: '生成口播文案',
          description: '把用户需求改写成适合 TTS 朗读的短文案。',
          model: 'deepseek-v4-flash',
          temperature: 0.6,
          maxOutputTokens: 500,
          timeoutSeconds: 45,
          systemPrompt:
            '你是中文短视频口播文案助手。只输出可直接朗读的正文，不要标题、编号、Markdown、解释或括号说明。句子要自然，适合 TTS 合成。',
          prompt:
            '根据下面需求生成一段中文口播文案，控制在 80 到 140 个汉字，结尾要有自然的行动引导。\n\n需求：{{voice_request}}',
          outputKey: 'speech_text',
          failurePolicy: 'continue',
          retryCount: 0,
        },
      },
      {
        id: 'tts-1',
        type: 'workflow',
        position: { x: 720, y: 170 },
        data: {
          kind: 'tts',
          ...nodeMeta.tts.defaults,
          label: '合成语音',
          description: '把大模型生成的口播文案转成音频地址。',
          ttsText: '{{speech_text}}',
          ttsModel: 'cosyvoice-v2',
          ttsVoice: 'longxiaochun_v2',
          audioFormat: 'mp3',
          speechRate: 1,
          outputKey: 'audio_url',
          failurePolicy: 'continue',
          retryCount: 0,
        },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 1060, y: 170 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '口播和音频',
          description: '同时返回口播正文和 TTS 音频地址。',
          prompt: '口播文案：\n{{speech_text}}\n\n音频结果：\n{{audio_url}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
      { id: 'e-llm-tts', source: 'llm-1', target: 'tts-1', animated: true },
      { id: 'e-tts-output', source: 'tts-1', target: 'output-1' },
    ],
  },
  {
    id: 'content-campaign-factory',
    name: '营销内容一键拆分',
    description: '大模型输出结构化 JSON，再拆成标题、口播、图片提示词和发布清单。',
    input: '为咖啡店新品燕麦拿铁做一套小红书推广内容，受众是上班族，语气温暖。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 180 },
        data: {
          kind: 'input',
          ...nodeMeta.input.defaults,
          label: '营销需求',
          sampleInput: '为咖啡店新品燕麦拿铁做一套小红书推广内容，受众是上班族，语气温暖。',
          outputKey: 'campaign_request',
        },
      },
      {
        id: 'llm-1',
        type: 'workflow',
        position: { x: 320, y: 180 },
        data: {
          kind: 'llm',
          ...nodeMeta.llm.defaults,
          label: '生成内容 JSON',
          model: 'deepseek-v4-flash',
          systemPrompt: '你是中文营销内容策划。只输出合法 JSON，不要 Markdown，不要解释。',
          prompt:
            '根据需求输出 JSON：{"title":"标题","script":"80字以内口播文案","image_prompt":"图片生成提示词","publish_checklist":["发布步骤1","发布步骤2","发布步骤3"]}\n需求：{{campaign_request}}',
          outputKey: 'content_json',
        },
      },
      {
        id: 'json-script',
        type: 'workflow',
        position: { x: 620, y: 80 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取口播',
          jsonSource: '{{content_json}}',
          jsonPath: 'script',
          outputKey: 'script',
        },
      },
      {
        id: 'json-image',
        type: 'workflow',
        position: { x: 620, y: 230 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取图片提示词',
          jsonSource: '{{content_json}}',
          jsonPath: 'image_prompt',
          outputKey: 'image_prompt',
        },
      },
      {
        id: 'json-checklist',
        type: 'workflow',
        position: { x: 620, y: 380 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取发布清单',
          jsonSource: '{{content_json}}',
          jsonPath: 'publish_checklist',
          outputKey: 'publish_checklist',
        },
      },
      {
        id: 'loop-1',
        type: 'workflow',
        position: { x: 920, y: 380 },
        data: {
          kind: 'loop',
          ...nodeMeta.loop.defaults,
          label: '格式化发布清单',
          loopItems: '{{publish_checklist}}',
          loopTemplate: '{{index}}. {{item}}',
          loopSeparator: '\n',
          outputKey: 'checklist_text',
        },
      },
      {
        id: 'aggregate-1',
        type: 'workflow',
        position: { x: 1220, y: 210 },
        data: {
          kind: 'aggregate',
          ...nodeMeta.aggregate.defaults,
          label: '聚合内容包',
          aggregateVariables: 'script\nimage_prompt\nchecklist_text',
          aggregateSeparator: '\n\n',
          outputKey: 'content_package',
        },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 1500, y: 210 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '营销内容包',
          prompt: '{{content_package}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
      { id: 'e-llm-script', source: 'llm-1', target: 'json-script' },
      { id: 'e-llm-image', source: 'llm-1', target: 'json-image' },
      { id: 'e-llm-checklist', source: 'llm-1', target: 'json-checklist' },
      { id: 'e-checklist-loop', source: 'json-checklist', target: 'loop-1' },
      { id: 'e-script-aggregate', source: 'json-script', target: 'aggregate-1' },
      { id: 'e-image-aggregate', source: 'json-image', target: 'aggregate-1' },
      { id: 'e-loop-aggregate', source: 'loop-1', target: 'aggregate-1' },
      { id: 'e-aggregate-output', source: 'aggregate-1', target: 'output-1' },
    ],
  },
  {
    id: 'feedback-triage',
    name: '用户反馈分诊',
    description: '把一段用户反馈分类为优先级、问题类型和行动项，适合产品/客服流转。',
    input: '用户说：最近 App 经常闪退，会员页也打不开，已经影响续费，希望尽快处理。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 180 },
        data: {
          kind: 'input',
          ...nodeMeta.input.defaults,
          label: '用户反馈',
          sampleInput: '用户说：最近 App 经常闪退，会员页也打不开，已经影响续费，希望尽快处理。',
          outputKey: 'feedback',
        },
      },
      {
        id: 'llm-1',
        type: 'workflow',
        position: { x: 320, y: 180 },
        data: {
          kind: 'llm',
          ...nodeMeta.llm.defaults,
          label: '分诊为 JSON',
          model: 'deepseek-v4-flash',
          systemPrompt: '你是产品运营分诊助手。只输出合法 JSON，不要 Markdown，不要解释。',
          prompt:
            '请把反馈分诊为 JSON：{"category":"问题类型","priority":"P0/P1/P2/P3","reason":"优先级原因","actions":["行动1","行动2","行动3"]}\n反馈：{{feedback}}',
          outputKey: 'triage_json',
        },
      },
      {
        id: 'json-priority',
        type: 'workflow',
        position: { x: 620, y: 70 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取优先级',
          jsonSource: '{{triage_json}}',
          jsonPath: 'priority',
          outputKey: 'priority',
        },
      },
      {
        id: 'json-actions',
        type: 'workflow',
        position: { x: 620, y: 260 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取行动项',
          jsonSource: '{{triage_json}}',
          jsonPath: 'actions',
          outputKey: 'actions',
        },
      },
      {
        id: 'loop-1',
        type: 'workflow',
        position: { x: 900, y: 260 },
        data: {
          kind: 'loop',
          ...nodeMeta.loop.defaults,
          label: '生成待办列表',
          loopItems: '{{actions}}',
          loopTemplate: '- [ ] {{item}}',
          loopSeparator: '\n',
          outputKey: 'todo_list',
        },
      },
      {
        id: 'template-1',
        type: 'workflow',
        position: { x: 1180, y: 180 },
        data: {
          kind: 'template',
          ...nodeMeta.template.defaults,
          label: '生成分诊卡片',
          templateText: '优先级：{{priority}}\n\n处理待办：\n{{todo_list}}\n\n原始反馈：\n{{feedback}}',
          outputKey: 'triage_card',
        },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 1460, y: 180 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '分诊结果',
          prompt: '{{triage_card}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
      { id: 'e-llm-priority', source: 'llm-1', target: 'json-priority' },
      { id: 'e-llm-actions', source: 'llm-1', target: 'json-actions' },
      { id: 'e-actions-loop', source: 'json-actions', target: 'loop-1' },
      { id: 'e-priority-template', source: 'json-priority', target: 'template-1' },
      { id: 'e-loop-template', source: 'loop-1', target: 'template-1' },
      { id: 'e-template-output', source: 'template-1', target: 'output-1' },
    ],
  },
  {
    id: 'meeting-action-items',
    name: '会议纪要待办提取',
    description: '从会议记录中提取摘要和待办清单，适合周会、项目会复盘。',
    input: '会议记录：本周完成登录改版，下周要补支付异常监控。张三负责接口告警，李四负责前端错误提示，周五前给测试版本。',
    nodes: [
      {
        id: 'input-1',
        type: 'workflow',
        position: { x: 40, y: 180 },
        data: {
          kind: 'input',
          ...nodeMeta.input.defaults,
          label: '会议记录',
          sampleInput: '会议记录：本周完成登录改版，下周要补支付异常监控。张三负责接口告警，李四负责前端错误提示，周五前给测试版本。',
          outputKey: 'meeting_notes',
        },
      },
      {
        id: 'llm-1',
        type: 'workflow',
        position: { x: 320, y: 180 },
        data: {
          kind: 'llm',
          ...nodeMeta.llm.defaults,
          label: '提取会议 JSON',
          model: 'deepseek-v4-flash',
          systemPrompt: '你是会议纪要助手。只输出合法 JSON，不要 Markdown，不要解释。',
          prompt:
            '从会议记录提取 JSON：{"summary":"一句话摘要","actions":["负责人 - 事项 - 截止时间","负责人 - 事项 - 截止时间"]}\n会议记录：{{meeting_notes}}',
          outputKey: 'meeting_json',
        },
      },
      {
        id: 'json-summary',
        type: 'workflow',
        position: { x: 620, y: 90 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取摘要',
          jsonSource: '{{meeting_json}}',
          jsonPath: 'summary',
          outputKey: 'summary',
        },
      },
      {
        id: 'json-actions',
        type: 'workflow',
        position: { x: 620, y: 280 },
        data: {
          kind: 'json',
          ...nodeMeta.json.defaults,
          label: '提取待办',
          jsonSource: '{{meeting_json}}',
          jsonPath: 'actions',
          outputKey: 'actions',
        },
      },
      {
        id: 'loop-1',
        type: 'workflow',
        position: { x: 900, y: 280 },
        data: {
          kind: 'loop',
          ...nodeMeta.loop.defaults,
          label: '格式化待办',
          loopItems: '{{actions}}',
          loopTemplate: '{{index}}. {{item}}',
          loopSeparator: '\n',
          outputKey: 'action_lines',
        },
      },
      {
        id: 'template-1',
        type: 'workflow',
        position: { x: 1180, y: 180 },
        data: {
          kind: 'template',
          ...nodeMeta.template.defaults,
          label: '生成纪要',
          templateText: '会议摘要：\n{{summary}}\n\n待办事项：\n{{action_lines}}',
          outputKey: 'meeting_report',
        },
      },
      {
        id: 'output-1',
        type: 'workflow',
        position: { x: 1460, y: 180 },
        data: {
          kind: 'output',
          ...nodeMeta.output.defaults,
          label: '会议纪要',
          prompt: '{{meeting_report}}',
          outputKey: 'answer',
        },
      },
    ],
    edges: [
      { id: 'e-input-llm', source: 'input-1', target: 'llm-1', animated: true },
      { id: 'e-llm-summary', source: 'llm-1', target: 'json-summary' },
      { id: 'e-llm-actions', source: 'llm-1', target: 'json-actions' },
      { id: 'e-actions-loop', source: 'json-actions', target: 'loop-1' },
      { id: 'e-summary-template', source: 'json-summary', target: 'template-1' },
      { id: 'e-loop-template', source: 'loop-1', target: 'template-1' },
      { id: 'e-template-output', source: 'template-1', target: 'output-1' },
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
  '给咖啡店新品燕麦拿铁写一段 20 秒中文口播，语气温暖、有购买引导。',
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
  archived: workflow.archived ?? false,
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
  archived: workflow.archived ?? false,
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

const readResponseErrorMessage = async (response: Response, fallback: string) => {
  try {
    const body = (await response.json()) as { detail?: string | Array<{ msg?: string }> }
    if (typeof body.detail === 'string' && body.detail.trim()) return body.detail
    if (Array.isArray(body.detail)) {
      const message = body.detail.map((item) => item.msg).filter(Boolean).join('；')
      if (message) return message
    }
  } catch {
    // Keep the caller's fallback when the response is not JSON.
  }
  return fallback
}

const getErrorMessage = (error: unknown, fallback: string) =>
  error instanceof Error && error.message ? error.message : fallback

const extractFirstUrl = (value: string) => value.match(/https?:\/\/[^\s)）"'，。]+/)?.[0]

const isAudioStep = (step: RunStep) => step.provider?.includes('TTS') || step.output.includes('音频地址')

const isSimulatedAudioStep = (step: RunStep) =>
  step.output.includes('模拟音频') || step.output.includes('模拟生成音频') || step.error?.includes('AliyunProviderError')

const invitationStatusLabel = (invitation: WorkspaceInvitationRecord) => {
  if (invitation.status === 'pending' && new Date(invitation.expires_at).getTime() <= Date.now()) return '已过期'
  const labels: Record<WorkspaceInvitationRecord['status'], string> = {
    pending: '待使用',
    accepted: '已接受',
    revoked: '已撤销',
    expired: '已过期',
  }
  return labels[invitation.status]
}

const canRevokeInvitation = (invitation: WorkspaceInvitationRecord) =>
  invitation.status === 'pending' && new Date(invitation.expires_at).getTime() > Date.now()

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

const loadAuthSession = (): AuthSession | null => {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as Partial<AuthSession>
    return parsed.token && parsed.user?.id ? (parsed as AuthSession) : null
  } catch {
    return null
  }
}

const persistAuthSession = (session: AuthSession | null) => {
  if (!session) {
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(session))
}

const loadActiveWorkspaceId = () => window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY) ?? ''

const persistActiveWorkspaceId = (workspaceId: string) => {
  if (!workspaceId) {
    window.localStorage.removeItem(ACTIVE_WORKSPACE_STORAGE_KEY)
    return
  }
  window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, workspaceId)
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

const getWorkflowSyncState = (workflow: WorkflowRecord): WorkflowSyncState => {
  if (!workflow.serverId) return 'local'
  if (!workflow.syncedAt) return 'synced'
  return new Date(workflow.updatedAt).getTime() > new Date(workflow.syncedAt).getTime() ? 'dirty' : 'synced'
}

const workflowSyncLabels: Record<WorkflowSyncState, string> = {
  local: '仅本地',
  synced: '已同步',
  dirty: '未同步改动',
}

const isServerWorkflowNewer = (workflow: WorkflowRecord, serverWorkflow: ServerWorkflowRecord) => {
  if (!workflow.syncedAt) return false
  return new Date(serverWorkflow.updated_at).getTime() > new Date(workflow.syncedAt).getTime()
}

const applyServerWorkflowToLocalRecord = (
  workflow: WorkflowRecord,
  serverWorkflow: ServerWorkflowRecord,
  syncedAt: string,
): WorkflowRecord => ({
  ...workflow,
  serverId: serverWorkflow.id,
  name: serverWorkflow.name,
  version: serverWorkflow.version || '0.2.0',
  nodes: serverWorkflow.nodes,
  edges: serverWorkflow.edges,
  archived: serverWorkflow.archived ?? false,
  updatedAt: serverWorkflow.updated_at,
  syncedAt,
})

const mergeBackendWorkflows = (
  current: WorkflowStore,
  imported: WorkflowRecord[],
  syncedAt: string,
): {
  store: WorkflowStore
  firstLoaded: WorkflowRecord
  appendedCount: number
  updatedCount: number
  conflictCount: number
} => {
  const importedByServerId = new Map(imported.map((workflow) => [workflow.serverId, workflow]))
  const existingServerIds = new Set(current.workflows.map((workflow) => workflow.serverId).filter(Boolean))
  let updatedCount = 0
  let conflictCount = 0
  const updatedExisting = current.workflows.map((workflow) => {
    const importedWorkflow = workflow.serverId ? importedByServerId.get(workflow.serverId) : undefined
    if (!importedWorkflow) return workflow
    if (getWorkflowSyncState(workflow) === 'dirty' && new Date(importedWorkflow.updatedAt).getTime() > new Date(workflow.syncedAt ?? 0).getTime()) {
      conflictCount += 1
      return workflow
    }
    updatedCount += 1
    return applyServerWorkflowToLocalRecord(
      workflow,
      {
        id: importedWorkflow.serverId ?? '',
        name: importedWorkflow.name,
        version: importedWorkflow.version,
        nodes: importedWorkflow.nodes,
        edges: importedWorkflow.edges,
        archived: importedWorkflow.archived,
        updated_at: importedWorkflow.updatedAt,
      },
      syncedAt,
    )
  })
  const appended = imported.filter((workflow) => !existingServerIds.has(workflow.serverId))
  const merged = [...updatedExisting, ...appended]
  const firstLoaded = merged.find((workflow) => workflow.serverId === imported[0].serverId) ?? appended[0] ?? merged[0]
  return {
    store: {
      activeWorkflowId: firstLoaded.id,
    workflows: merged,
    },
    firstLoaded,
    appendedCount: appended.length,
    updatedCount,
    conflictCount,
  }
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

const parseJsonPathValue = (source: string, path: string) => {
  const parsed = JSON.parse(source)
  const normalizedPath = path.trim()
  if (!normalizedPath) return parsed
  return normalizedPath.split('.').reduce((current: unknown, part) => {
    if (current === undefined || current === null) return undefined
    if (Array.isArray(current)) return current[Number(part)]
    if (typeof current === 'object') return (current as Record<string, unknown>)[part]
    return undefined
  }, parsed as unknown)
}

const formatWorkflowValue = (value: unknown) =>
  typeof value === 'string' ? value : JSON.stringify(value, null, 2)

const evaluateCodeExpression = (expression: string, context: Record<string, string>) => {
  const helpers: Record<string, (value: string) => string> = {
    upper: (value) => value.toUpperCase(),
    lower: (value) => value.toLowerCase(),
    trim: (value) => value.trim(),
    length: (value) => String(value.length),
  }
  const functionMatch = expression.trim().match(/^(\w+)\(([\w.-]+)\)$/)
  if (functionMatch) {
    const helper = helpers[functionMatch[1]]
    if (!helper) throw new Error(`不支持的函数：${functionMatch[1]}`)
    return helper(context[functionMatch[2]] ?? '')
  }
  return renderTemplate(expression, context)
}

const parseLoopItems = (value: string) => {
  const trimmed = value.trim()
  if (!trimmed) return [] as string[]
  try {
    const parsed = JSON.parse(trimmed)
    if (Array.isArray(parsed)) return parsed.map((item) => formatWorkflowValue(item))
  } catch {
    // Fall through to line splitting.
  }
  return trimmed.split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean)
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
  if (data.kind === 'assign' && !data.assignmentValue?.trim()) {
    issues.push({ field: 'assignmentValue', level: 'warning', message: '建议填写要赋值的文本或模板。' })
  }
  if (data.kind === 'template' && !data.templateText?.trim()) {
    issues.push({ field: 'templateText', level: 'warning', message: '建议填写文本模板。' })
  }
  if (data.kind === 'json' && !data.jsonSource?.trim()) {
    issues.push({ field: 'jsonSource', level: 'error', message: 'JSON 解析节点需要填写 JSON 来源。' })
  }
  if (data.kind === 'code' && !data.codeExpression?.trim()) {
    issues.push({ field: 'codeExpression', level: 'error', message: '代码执行节点需要填写表达式。' })
  }
  if (data.kind === 'loop' && !data.loopItems?.trim()) {
    issues.push({ field: 'loopItems', level: 'error', message: '循环节点需要填写列表来源。' })
  }
  if (data.kind === 'aggregate' && !data.aggregateVariables?.trim()) {
    issues.push({ field: 'aggregateVariables', level: 'warning', message: '建议填写要聚合的变量名。' })
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

  if (data.kind === 'tts') {
    if (!data.ttsText?.trim()) {
      issues.push({ field: 'ttsText', level: 'warning', message: '建议填写要合成语音的文本。' })
    }
    if (data.speechRate !== undefined && (Number.isNaN(data.speechRate) || data.speechRate < 0.5 || data.speechRate > 2)) {
      issues.push({ field: 'speechRate', level: 'error', message: '语速需要在 0.5 到 2.0 之间。' })
    }
  }

  if (data.kind === 'image') {
    if (!data.imagePrompt?.trim()) {
      issues.push({ field: 'imagePrompt', level: 'warning', message: '建议填写图片生成提示词。' })
    }
    if (
      data.imageCount !== undefined &&
      (!Number.isInteger(data.imageCount) || data.imageCount < 1 || data.imageCount > 4)
    ) {
      issues.push({ field: 'imageCount', level: 'error', message: '生成数量需要在 1 到 4 之间。' })
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
  const [authSession, setAuthSession] = useState<AuthSession | null>(() => loadAuthSession())
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [authUsername, setAuthUsername] = useState('')
  const [authPassword, setAuthPassword] = useState('')
  const [authNotice, setAuthNotice] = useState('')
  const [backendStatus, setBackendStatus] = useState<'unknown' | 'online' | 'offline'>('unknown')
  const [workflowSearch, setWorkflowSearch] = useState('')
  const [workflowSortMode, setWorkflowSortMode] = useState<WorkflowSortMode>('updated')
  const [showArchivedWorkflows, setShowArchivedWorkflows] = useState(false)
  const [runHistorySearch, setRunHistorySearch] = useState('')
  const [runHistoryStatusFilter, setRunHistoryStatusFilter] = useState<RunHistoryStatusFilter>('all')
  const [adminView, setAdminView] = useState<AdminView>('node')
  const [adminOverview, setAdminOverview] = useState<AdminOverviewRecord | null>(null)
  const [adminOverviewBusy, setAdminOverviewBusy] = useState(false)
  const [remoteValidation, setRemoteValidation] = useState<RemoteValidationState | null>(null)
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null)
  const [providerStatusCheckedAt, setProviderStatusCheckedAt] = useState('')
  const [modelConfig, setModelConfig] = useState<ModelConfigRecord | null>(null)
  const [aliyunConfig, setAliyunConfig] = useState<ProviderConfigState>({
    record: null,
    form: createDefaultProviderConfigForm('aliyun'),
  })
  const [paismartConfig, setPaismartConfig] = useState<ProviderConfigState>({
    record: null,
    form: { ...PAISMART_CONFIG_DEFAULTS },
  })
  const [modelConfigForm, setModelConfigForm] = useState(createDefaultProviderConfigForm('deepseek'))
  const [modelConfigFeedback, setModelConfigFeedback] = useState<ModelConfigFeedback | null>(null)
  const [modelConfigBusy, setModelConfigBusy] = useState<ModelConfigAction | null>(null)
  const [knowledgeStatus, setKnowledgeStatus] = useState<KnowledgeStatus | null>(null)
  const [knowledgeDocuments, setKnowledgeDocuments] = useState<KnowledgeDocument[]>([])
  const [workspaces, setWorkspaces] = useState<WorkspaceRecord[]>([])
  const [activeWorkspaceId, setActiveWorkspaceId] = useState(() => loadActiveWorkspaceId())
  const [workspaceMembers, setWorkspaceMembers] = useState<WorkspaceMemberRecord[]>([])
  const [workspaceInvitations, setWorkspaceInvitations] = useState<WorkspaceInvitationRecord[]>([])
  const [invitationRole, setInvitationRole] = useState<WorkspaceRecord['role']>('viewer')
  const [invitationCodeInput, setInvitationCodeInput] = useState('')
  const [workspaceInviteBusy, setWorkspaceInviteBusy] = useState<'load' | 'create' | 'accept' | 'revoke' | null>(null)
  const [workspaceMemberBusy, setWorkspaceMemberBusy] = useState<'load' | 'role' | 'remove' | null>(null)
  const [workflowVersions, setWorkflowVersions] = useState<WorkflowVersionRecord[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLogRecord[]>([])
  const [versionNote, setVersionNote] = useState('')
  const [workflowMetaBusy, setWorkflowMetaBusy] = useState<'versions' | 'audit' | 'save-version' | 'restore' | null>(null)
  const [runJobs, setRunJobs] = useState<RunJobRecord[]>([])
  const [activeRunJobId, setActiveRunJobId] = useState('')
  const [lastBackendSyncAt, setLastBackendSyncAt] = useState('')
  const nextNodeId = useRef(1)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const knowledgeFileInputRef = useRef<HTMLInputElement | null>(null)
  const flowInstanceRef = useRef<{ setCenter: (x: number, y: number, options?: { duration?: number; zoom?: number }) => void } | null>(null)
  const didAutoLoadBackendRef = useRef(false)

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
          const syncRank: Record<WorkflowSyncState, number> = { dirty: 3, local: 2, synced: 1 }
          const syncCompare = syncRank[getWorkflowSyncState(b)] - syncRank[getWorkflowSyncState(a)]
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
  const activeWorkflowSyncState = getWorkflowSyncState(activeWorkflow)
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

  const deepseekWorkspaceConfigured = Boolean(modelConfig?.enabled && modelConfig.has_api_key)
  const aliyunWorkspaceConfigured = Boolean(aliyunConfig.record?.enabled && aliyunConfig.record.has_api_key)
  const paismartWorkspaceConfigured = Boolean(paismartConfig.record?.enabled && paismartConfig.record.has_api_key)
  const deepseekConfigured = Boolean(providerStatus?.deepseek_configured || deepseekWorkspaceConfigured)
  const aliyunConfigured = Boolean(providerStatus?.aliyun_configured || aliyunWorkspaceConfigured)
  const hasRealModelProvider = Boolean(deepseekConfigured || providerStatus?.openai_configured || aliyunConfigured)
  const activeProviderLabel = deepseekConfigured
    ? deepseekWorkspaceConfigured
      ? `DeepSeek 工作区 - ${modelConfig?.model ?? 'deepseek-v4-flash'}`
      : `DeepSeek - ${providerStatus?.deepseek_model ?? 'deepseek-v4-flash'}`
    : providerStatus?.openai_configured
      ? `OpenAI - ${providerStatus.openai_default_model}`
      : aliyunConfigured
        ? aliyunWorkspaceConfigured
          ? `阿里云工作区 - ${aliyunConfig.record?.model ?? 'cosyvoice-v2'}`
          : `阿里云 - ${providerStatus?.aliyun_tts_model ?? '多模态'}`
        : '模拟输出'
  const knowledgeStatusLabel = knowledgeStatus
    ? `${knowledgeStatus.document_count} 个文档 / ${knowledgeStatus.chunk_count} 个片段`
    : '未检查'
  const activeWorkspace = workspaces.find((workspace) => workspace.id === activeWorkspaceId) ?? workspaces[0]
  const activeRunJob = runJobs.find((job) => job.id === activeRunJobId)
  const runJobStatusLabels: Record<RunJobRecord['status'], string> = {
    queued: '排队中',
    running: '运行中',
    succeeded: '已完成',
    failed: '失败',
    canceled: '已取消',
  }
  const authToken = authSession?.token

  const updateModelConfigForm = (patch: Partial<typeof modelConfigForm>) => {
    setModelConfigForm((current) => ({ ...current, ...patch }))
  }

  const updateAliyunConfigForm = (patch: Partial<ProviderConfigState['form']>) => {
    setAliyunConfig((current) => ({
      ...current,
      form: { ...current.form, ...patch },
    }))
  }

  const updatePaismartConfigForm = (patch: Partial<ProviderConfigState['form']>) => {
    setPaismartConfig((current) => ({
      ...current,
      form: { ...current.form, ...patch },
    }))
  }

  const clearSessionState = useCallback(() => {
    setAuthSession(null)
    persistAuthSession(null)
    setBackendStatus('unknown')
    setProviderStatus(null)
    setModelConfig(null)
    setModelConfigForm(createDefaultProviderConfigForm('deepseek'))
    setAliyunConfig({
      record: null,
      form: createDefaultProviderConfigForm('aliyun'),
    })
    setPaismartConfig({
      record: null,
      form: { ...PAISMART_CONFIG_DEFAULTS },
    })
    setKnowledgeStatus(null)
    setKnowledgeDocuments([])
    setWorkspaces([])
    setActiveWorkspaceId('')
    persistActiveWorkspaceId('')
    setAdminOverview(null)
    setWorkspaceMembers([])
    setWorkspaceInvitations([])
    setInvitationCodeInput('')
    setRunJobs([])
    setActiveRunJobId('')
    setRunHistory([])
    setSelectedRunId('')
    setWorkflowVersions([])
    setAuditLogs([])
    setVersionNote('')
  }, [])

  const apiFetch = useCallback(
    async (path: string, init: RequestInit = {}) => {
      const headers = new Headers(init.headers)
      if (authToken) {
        headers.set('Authorization', `Bearer ${authToken}`)
      }
      if (activeWorkspaceId) {
        headers.set('X-Workspace-Id', activeWorkspaceId)
      }
      const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
      if (response.status === 401 && authToken && !path.startsWith('/api/auth/')) {
        clearSessionState()
        setNotice('登录已过期，请重新登录。')
      }
      return response
    },
    [activeWorkspaceId, authToken, clearSessionState],
  )

  const handleAuthSubmit = async () => {
    setAuthNotice('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/${authMode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: authUsername.trim(), password: authPassword }),
      })
      if (!response.ok) throw new Error('auth failed')
      const session = (await response.json()) as AuthSession
      setAuthSession(session)
      persistAuthSession(session)
      setAuthPassword('')
      setNotice(`已登录：${session.user.username}`)
    } catch {
      setAuthNotice(authMode === 'login' ? '登录失败：请检查账号和密码。' : '注册失败：账号可能已存在。')
    }
  }

  const loadWorkspaces = useCallback(async () => {
    if (!authToken) return [] as WorkspaceRecord[]
    try {
      const response = await apiFetch('/api/workspaces')
      if (!response.ok) throw new Error('load workspaces failed')
      const records = (await response.json()) as WorkspaceRecord[]
      setWorkspaces(records)
      const storedWorkspaceId = loadActiveWorkspaceId()
      const nextActiveWorkspaceId = records.some((workspace) => workspace.id === storedWorkspaceId)
        ? storedWorkspaceId
        : records[0]?.id ?? ''
      setActiveWorkspaceId(nextActiveWorkspaceId)
      persistActiveWorkspaceId(nextActiveWorkspaceId)
      return records
    } catch {
      setWorkspaces([])
      setNotice('团队空间读取失败：请确认后端服务在线。')
      return []
    }
  }, [apiFetch, authToken])

  const logout = async () => {
    try {
      await apiFetch('/api/auth/logout', { method: 'POST' })
    } catch {
      // Local logout still clears the browser session.
    }
    clearSessionState()
    setNotice('已退出登录。')
  }

  const loadAdminOverview = useCallback(async (showNotice = true) => {
    if (!activeWorkspaceId) {
      setAdminOverview(null)
      return
    }
    setAdminOverviewBusy(true)
    try {
      const response = await apiFetch('/api/admin/overview')
      if (!response.ok) throw new Error('load admin overview failed')
      const overview = (await response.json()) as AdminOverviewRecord
      setAdminOverview({ ...overview, run_metrics: overview.run_metrics ?? createEmptyRunMetrics() })
      if (showNotice) setNotice('已刷新系统概览。')
    } catch {
      setAdminOverview(null)
      if (showNotice) setNotice('系统概览读取失败：请确认后端在线。')
    } finally {
      setAdminOverviewBusy(false)
    }
  }, [activeWorkspaceId, apiFetch])

  const loadWorkspaceMembers = useCallback(async () => {
    if (!activeWorkspaceId) {
      setWorkspaceMembers([])
      return
    }
    setWorkspaceMemberBusy('load')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/members`)
      if (!response.ok) throw new Error('load members failed')
      setWorkspaceMembers((await response.json()) as WorkspaceMemberRecord[])
    } catch {
      setWorkspaceMembers([])
      setNotice('读取团队成员失败：请确认你有当前团队空间访问权限。')
    } finally {
      setWorkspaceMemberBusy(null)
    }
  }, [activeWorkspaceId, apiFetch])

  const updateWorkspaceMemberRole = async (member: WorkspaceMemberRecord, role: WorkspaceRecord['role']) => {
    if (!activeWorkspaceId || member.role === role) return
    setWorkspaceMemberBusy('role')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/members`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: member.username, role }),
      })
      if (!response.ok) throw new Error('update member role failed')
      const updated = (await response.json()) as WorkspaceMemberRecord
      setWorkspaceMembers((current) => current.map((item) => (item.id === updated.id ? updated : item)))
      setNotice(`已将 ${updated.username} 设置为 ${updated.role}。`)
    } catch {
      setNotice('修改成员角色失败：只有 owner 可以管理成员。')
    } finally {
      setWorkspaceMemberBusy(null)
    }
  }

  const removeWorkspaceMember = async (member: WorkspaceMemberRecord) => {
    if (!activeWorkspaceId) return
    setWorkspaceMemberBusy('remove')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/members/${member.id}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('remove member failed')
      const removed = (await response.json()) as WorkspaceMemberRecord
      setWorkspaceMembers((current) => current.filter((item) => item.id !== removed.id))
      setNotice(`已移除成员 ${removed.username}。`)
    } catch {
      setNotice('移除成员失败：不能移除自己或最后一个 owner。')
    } finally {
      setWorkspaceMemberBusy(null)
    }
  }

  const loadWorkspaceInvitations = useCallback(async () => {
    if (!activeWorkspaceId || activeWorkspace?.role !== 'owner') {
      setWorkspaceInvitations([])
      return
    }
    setWorkspaceInviteBusy('load')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/invitations`)
      if (!response.ok) throw new Error('load invitations failed')
      setWorkspaceInvitations((await response.json()) as WorkspaceInvitationRecord[])
    } catch {
      setNotice('读取团队邀请失败：请确认你是当前团队空间 owner。')
    } finally {
      setWorkspaceInviteBusy(null)
    }
  }, [activeWorkspace?.role, activeWorkspaceId, apiFetch])

  const createWorkspaceInvitation = async () => {
    if (!activeWorkspaceId) return
    setWorkspaceInviteBusy('create')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/invitations`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role: invitationRole }),
      })
      if (!response.ok) throw new Error('create invitation failed')
      const invitation = (await response.json()) as WorkspaceInvitationRecord
      setWorkspaceInvitations((current) => [invitation, ...current])
      setNotice(`已创建 ${invitation.role} 邀请码，可复制给对方使用。`)
    } catch {
      setNotice('创建邀请码失败：只有 owner 可以创建邀请。')
    } finally {
      setWorkspaceInviteBusy(null)
    }
  }

  const acceptWorkspaceInvitation = async () => {
    const code = invitationCodeInput.trim()
    if (!code) {
      setNotice('请先输入邀请码。')
      return
    }
    setWorkspaceInviteBusy('accept')
    try {
      const response = await apiFetch('/api/workspaces/invitations/accept', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (!response.ok) throw new Error('accept invitation failed')
      const invitation = (await response.json()) as WorkspaceInvitationRecord
      setInvitationCodeInput('')
      await loadWorkspaces()
      setNotice(`已加入团队空间：${invitation.workspace_name ?? invitation.workspace_id}`)
    } catch {
      setNotice('加入团队失败：邀请码不存在、已使用或已撤销。')
    } finally {
      setWorkspaceInviteBusy(null)
    }
  }

  const revokeWorkspaceInvitation = async (invitationId: string) => {
    if (!activeWorkspaceId) return
    setWorkspaceInviteBusy('revoke')
    try {
      const response = await apiFetch(`/api/workspaces/${activeWorkspaceId}/invitations/${invitationId}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('revoke invitation failed')
      const invitation = (await response.json()) as WorkspaceInvitationRecord
      setWorkspaceInvitations((current) =>
        current.map((item) => (item.id === invitation.id ? invitation : item)),
      )
      setNotice('已撤销邀请码。')
    } catch {
      setNotice('撤销邀请码失败：请确认你是当前团队空间 owner。')
    } finally {
      setWorkspaceInviteBusy(null)
    }
  }

  useEffect(() => {
    if (!authSession) return
    const controller = new AbortController()
    const currentKey = validationKey

    const timer = window.setTimeout(async () => {
      try {
        const response = await apiFetch('/api/workflows/validate', {
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
  }, [activeWorkflow, apiFetch, authSession, localWorkflowIssues, validationKey])

  const validateActiveWorkflow = async () => {
    const currentKey = validationKey
    try {
      const response = await apiFetch('/api/workflows/validate', {
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
          `耗时：${step.duration_ms ?? 0}ms`,
          `尝试：${step.attempt_count ?? 1} 次`,
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
            : status.aliyun_configured
              ? `阿里云多模态已启用：TTS ${status.aliyun_tts_model ?? '默认'}，图片 ${status.aliyun_image_model ?? '默认'}。`
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

  const applyProviderConfig = useCallback((provider: ProviderConfigKey, config: ModelConfigRecord) => {
    const defaults = PROVIDER_CONFIG_DEFAULTS[provider]
    const form = {
      ...defaults,
      enabled: config.has_api_key || config.updated_at ? config.enabled : defaults.enabled,
      model: config.model || defaults.model,
      baseUrl: config.base_url || defaults.baseUrl,
      apiKey: '',
    }

    if (provider === 'deepseek') {
      setModelConfig(config)
      setModelConfigForm(form)
    } else {
      setAliyunConfig({ record: config, form })
    }
  }, [])

  const applyPaismartConfig = useCallback((config: ModelConfigRecord) => {
    const form = {
      ...PAISMART_CONFIG_DEFAULTS,
      enabled: config.has_api_key || config.updated_at ? config.enabled : PAISMART_CONFIG_DEFAULTS.enabled,
      model: config.model || PAISMART_CONFIG_DEFAULTS.model,
      baseUrl: config.base_url || PAISMART_CONFIG_DEFAULTS.baseUrl,
      apiKey: '',
    }
    setPaismartConfig({ record: config, form })
  }, [])

  const loadProviderModelConfig = useCallback(async (provider: ProviderConfigKey, showNotice = false) => {
    if (!authSession || !activeWorkspaceId) return null
    const label = PROVIDER_CONFIG_LABELS[provider]
    if (showNotice) {
      setModelConfigBusy('load')
      setModelConfigFeedback({ provider, type: 'info', text: `正在读取当前团队空间的 ${label} 配置...` })
    }
    try {
      const response = await apiFetch(`/api/model-configs/${provider}`)
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, `读取 ${label} 配置失败：请确认后端在线。`))
      }
      const config = (await response.json()) as ModelConfigRecord
      applyProviderConfig(provider, config)
      if (showNotice) {
        const message = `已读取当前团队空间的 ${label} 配置。`
        setModelConfigFeedback({ provider, type: 'ok', text: message })
        setNotice(message)
      }
      return config
    } catch (error) {
      const message = getErrorMessage(error, `读取 ${label} 配置失败：请确认后端在线。`)
      if (provider === 'deepseek') {
        setModelConfig(null)
      } else {
        setAliyunConfig((current) => ({ ...current, record: null }))
      }
      if (showNotice) {
        setModelConfigFeedback({ provider, type: 'error', text: message })
        setNotice(message)
      }
      return null
    } finally {
      if (showNotice) setModelConfigBusy(null)
    }
  }, [activeWorkspaceId, apiFetch, applyProviderConfig, authSession])

  const loadModelConfig = useCallback(
    (showNotice = false) => loadProviderModelConfig('deepseek', showNotice),
    [loadProviderModelConfig],
  )

  const loadAliyunConfig = useCallback(
    (showNotice = false) => loadProviderModelConfig('aliyun', showNotice),
    [loadProviderModelConfig],
  )

  const loadPaismartConfig = useCallback(async (showNotice = false) => {
    if (!authSession || !activeWorkspaceId) return null
    const label = PROVIDER_CONFIG_LABELS.paismart
    if (showNotice) {
      setModelConfigBusy('load')
      setModelConfigFeedback({ provider: 'paismart', type: 'info', text: `正在读取当前团队空间的 ${label} 配置...` })
    }
    try {
      const response = await apiFetch('/api/model-configs/paismart')
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, `读取 ${label} 配置失败：请确认后端在线。`))
      }
      const config = (await response.json()) as ModelConfigRecord
      applyPaismartConfig(config)
      if (showNotice) {
        const message = `已读取当前团队空间的 ${label} 配置。`
        setModelConfigFeedback({ provider: 'paismart', type: 'ok', text: message })
        setNotice(message)
      }
      return config
    } catch (error) {
      const message = getErrorMessage(error, `读取 ${label} 配置失败：请确认后端在线。`)
      setPaismartConfig((current) => ({ ...current, record: null }))
      if (showNotice) {
        setModelConfigFeedback({ provider: 'paismart', type: 'error', text: message })
        setNotice(message)
      }
      return null
    } finally {
      if (showNotice) setModelConfigBusy(null)
    }
  }, [activeWorkspaceId, apiFetch, applyPaismartConfig, authSession])

  const persistProviderModelConfig = async (provider: ProviderConfigKey) => {
    if (!activeWorkspaceId) {
      throw new Error('请先选择团队空间。')
    }
    const label = PROVIDER_CONFIG_LABELS[provider]
    const currentRecord = provider === 'deepseek' ? modelConfig : aliyunConfig.record
    const currentForm = provider === 'deepseek' ? modelConfigForm : aliyunConfig.form
    if (!currentRecord?.has_api_key && !currentForm.apiKey.trim()) {
      throw new Error(`首次保存 ${label} 配置时需要填写 API Key。`)
    }
    const response = await apiFetch(`/api/model-configs/${provider}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: currentForm.enabled,
        model: currentForm.model,
        base_url: currentForm.baseUrl,
        api_key: currentForm.apiKey.trim() || null,
      }),
    })
    if (!response.ok) {
      throw new Error(await readResponseErrorMessage(response, `保存 ${label} 配置失败：请确认你有当前团队空间的编辑权限。`))
    }
    const config = (await response.json()) as ModelConfigRecord
    applyProviderConfig(provider, config)
    await refreshProviderStatus(false)
    return config
  }

  const saveProviderModelConfig = async (provider: ProviderConfigKey) => {
    if (modelConfigBusy) return
    const label = PROVIDER_CONFIG_LABELS[provider]
    setModelConfigBusy('save')
    setModelConfigFeedback({ provider, type: 'info', text: `正在保存 ${label} 配置...` })
    try {
      await persistProviderModelConfig(provider)
      const message = `已保存当前团队空间的 ${label} 配置。`
      setModelConfigFeedback({ provider, type: 'ok', text: message })
      setNotice(message)
    } catch (error) {
      const message = getErrorMessage(error, `保存 ${label} 配置失败：请确认你有当前团队空间的编辑权限。`)
      setModelConfigFeedback({ provider, type: 'error', text: message })
      setNotice(message)
    } finally {
      setModelConfigBusy(null)
    }
  }

  const testProviderModelConfig = async (provider: ProviderConfigKey) => {
    if (modelConfigBusy) return
    const label = PROVIDER_CONFIG_LABELS[provider]
    const currentForm = provider === 'deepseek' ? modelConfigForm : aliyunConfig.form
    const hasNewApiKey = Boolean(currentForm.apiKey.trim())
    setModelConfigBusy('test')
    setModelConfigFeedback({
      provider,
      type: 'info',
      text: hasNewApiKey ? '检测到新的 API Key，正在先保存再测试...' : `正在测试当前团队空间的 ${label} 配置...`,
    })
    try {
      if (hasNewApiKey) {
        await persistProviderModelConfig(provider)
      }
      const response = await apiFetch(`/api/model-configs/${provider}/test`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, `${label} 配置测试失败：请确认后端在线。`))
      }
      const result = (await response.json()) as { ok: boolean; message: string }
      setModelConfigFeedback({ provider, type: result.ok ? 'ok' : 'error', text: result.message })
      setNotice(result.message)
      if (result.ok) await refreshProviderStatus(false)
    } catch (error) {
      const message = getErrorMessage(error, `${label} 配置测试失败：请确认后端在线，且你有当前团队空间的编辑权限。`)
      setModelConfigFeedback({ provider, type: 'error', text: message })
      setNotice(message)
    } finally {
      setModelConfigBusy(null)
    }
  }

  const saveModelConfig = () => saveProviderModelConfig('deepseek')
  const testModelConfig = () => testProviderModelConfig('deepseek')
  const saveAliyunConfig = () => saveProviderModelConfig('aliyun')
  const testAliyunConfig = () => testProviderModelConfig('aliyun')

  const persistPaismartConfig = async () => {
    if (!activeWorkspaceId) {
      throw new Error('请先选择团队空间。')
    }
    if (!paismartConfig.record?.has_api_key && !paismartConfig.form.apiKey.trim()) {
      throw new Error('首次保存 PaiSmart RAG 配置时需要填写 Token；如果服务不需要 Token，可以填写 none。')
    }
    const response = await apiFetch('/api/model-configs/paismart', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        enabled: paismartConfig.form.enabled,
        model: paismartConfig.form.model,
        base_url: paismartConfig.form.baseUrl,
        api_key: paismartConfig.form.apiKey.trim() || null,
      }),
    })
    if (!response.ok) {
      throw new Error(await readResponseErrorMessage(response, '保存 PaiSmart RAG 配置失败：请确认你有当前团队空间的编辑权限。'))
    }
    const config = (await response.json()) as ModelConfigRecord
    applyPaismartConfig(config)
    await refreshProviderStatus(false)
    return config
  }

  const savePaismartConfig = async () => {
    if (modelConfigBusy) return
    setModelConfigBusy('save')
    setModelConfigFeedback({ provider: 'paismart', type: 'info', text: '正在保存 PaiSmart RAG 配置...' })
    try {
      await persistPaismartConfig()
      const message = '已保存当前团队空间的 PaiSmart RAG 配置。'
      setModelConfigFeedback({ provider: 'paismart', type: 'ok', text: message })
      setNotice(message)
    } catch (error) {
      const message = getErrorMessage(error, '保存 PaiSmart RAG 配置失败：请确认你有当前团队空间的编辑权限。')
      setModelConfigFeedback({ provider: 'paismart', type: 'error', text: message })
      setNotice(message)
    } finally {
      setModelConfigBusy(null)
    }
  }

  const testPaismartConfig = async () => {
    if (modelConfigBusy) return
    const hasNewApiKey = Boolean(paismartConfig.form.apiKey.trim())
    setModelConfigBusy('test')
    setModelConfigFeedback({
      provider: 'paismart',
      type: 'info',
      text: hasNewApiKey ? '检测到新的 Token，正在先保存再测试...' : '正在测试当前团队空间的 PaiSmart RAG 配置...',
    })
    try {
      if (hasNewApiKey) {
        await persistPaismartConfig()
      }
      const response = await apiFetch('/api/model-configs/paismart/test', { method: 'POST' })
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, 'PaiSmart RAG 配置测试失败：请确认后端在线。'))
      }
      const result = (await response.json()) as { ok: boolean; message: string }
      setModelConfigFeedback({ provider: 'paismart', type: result.ok ? 'ok' : 'error', text: result.message })
      setNotice(result.message)
      if (result.ok) await refreshProviderStatus(false)
    } catch (error) {
      const message = getErrorMessage(error, 'PaiSmart RAG 配置测试失败：请确认后端在线，且你有当前团队空间的编辑权限。')
      setModelConfigFeedback({ provider: 'paismart', type: 'error', text: message })
      setNotice(message)
    } finally {
      setModelConfigBusy(null)
    }
  }

  const refreshKnowledgeStatus = async (showNotice = true) => {
    try {
      const response = await apiFetch('/api/knowledge/status')
      if (!response.ok) throw new Error('knowledge status failed')
      const status = (await response.json()) as KnowledgeStatus
      setKnowledgeStatus(status)
      const documentsResponse = await apiFetch('/api/knowledge/documents')
      if (documentsResponse.ok) {
        setKnowledgeDocuments((await documentsResponse.json()) as KnowledgeDocument[])
      }
      setBackendStatus('online')
      if (showNotice) {
        setNotice(`本地知识库已加载 ${status.document_count} 个文档，${status.chunk_count} 个片段。`)
      }
      return status
    } catch {
      setKnowledgeStatus(null)
      setKnowledgeDocuments([])
      setBackendStatus('offline')
      if (showNotice) setNotice('知识库状态读取失败：请确认后端在线。')
      return null
    }
  }

  const uploadKnowledgeDocument = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!/\.(md|txt)$/i.test(file.name)) {
      setNotice('知识库只支持上传 .md 或 .txt 文件。')
      return
    }

    try {
      const content = await file.text()
      const response = await apiFetch('/api/knowledge/documents', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: file.name, content }),
      })
      if (!response.ok) throw new Error('upload knowledge failed')
      await refreshKnowledgeStatus(false)
      setNotice(`已上传知识文档：${file.name}`)
    } catch {
      setBackendStatus('offline')
      setNotice('上传知识文档失败：请确认后端在线，且文件小于 1MB。')
    }
  }

  const deleteKnowledgeDocument = async (name: string) => {
    try {
      const response = await apiFetch(`/api/knowledge/documents/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      if (!response.ok) throw new Error('delete knowledge failed')
      await refreshKnowledgeStatus(false)
      setNotice(`已删除知识文档：${name}`)
    } catch {
      setNotice('删除知识文档失败：请确认后端在线。')
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
    field:
      | 'prompt'
      | 'systemPrompt'
      | 'assignmentValue'
      | 'templateText'
      | 'jsonSource'
      | 'codeExpression'
      | 'loopItems'
      | 'loopTemplate'
      | 'aggregateVariables'
      | 'query'
      | 'toolUrl'
      | 'toolHeaders'
      | 'toolParams'
      | 'ttsText'
      | 'imagePrompt'
      | 'conditionValue',
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

  const syncWorkflowToBackend = async (workflow: WorkflowRecord): Promise<WorkflowRecord> => {
    let targetWorkflow = workflow
    if (workflow.serverId) {
      const latestResponse = await apiFetch(`/api/workflows/${workflow.serverId}`)
      if (latestResponse.ok) {
        const latest = (await latestResponse.json()) as ServerWorkflowRecord
        if (isServerWorkflowNewer(workflow, latest)) {
          throw new Error('remote_newer')
        }
      } else if (latestResponse.status === 404) {
        targetWorkflow = {
          id: workflow.id,
          name: workflow.name,
          version: workflow.version,
          nodes: workflow.nodes,
          edges: workflow.edges,
          archived: workflow.archived,
          updatedAt: workflow.updatedAt,
        }
      } else if (latestResponse.status !== 404) {
        throw new Error('sync failed')
      }
    }

    const method = targetWorkflow.serverId ? 'PUT' : 'POST'
    const url = targetWorkflow.serverId
      ? `${API_BASE_URL}/api/workflows/${targetWorkflow.serverId}`
      : `${API_BASE_URL}/api/workflows`
    const response = await apiFetch(url.replace(API_BASE_URL, ''), {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(workflowToServerPayload(targetWorkflow)),
    })
    if (!response.ok) {
      const validation = await readValidationError(response)
      if (validation) {
        const issues = [...validation.errors, ...validation.warnings].map(serverIssueToWorkflowIssue)
        setRemoteValidation({ issues, key: createValidationKey(workflow), status: 'backend' })
        showBlockingIssues(issues, '同步')
        throw new Error('validation failed')
      }
      throw new Error('sync failed')
    }

    const saved = (await response.json()) as ServerWorkflowRecord
    const syncedAt = new Date().toISOString()
    return applyServerWorkflowToLocalRecord(workflow, saved, syncedAt)
  }

  const loadWorkflowVersions = useCallback(async (workflowId = activeWorkflow.serverId, showNotice = true) => {
    if (!workflowId) {
      setWorkflowVersions([])
      if (showNotice) setNotice('当前工作流还没有同步到后端，暂无版本历史。')
      return []
    }
    setWorkflowMetaBusy('versions')
    try {
      const response = await apiFetch(`/api/workflows/${workflowId}/versions`)
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, '读取版本历史失败。'))
      }
      const versions = (await response.json()) as WorkflowVersionRecord[]
      setWorkflowVersions(versions)
      setBackendStatus('online')
      if (showNotice) setNotice(`已加载 ${versions.length} 个工作流版本。`)
      return versions
    } catch (error) {
      const message = getErrorMessage(error, '读取版本历史失败：请确认后端在线。')
      setBackendStatus('offline')
      if (showNotice) setNotice(message)
      return []
    } finally {
      setWorkflowMetaBusy(null)
    }
  }, [activeWorkflow.serverId, apiFetch])

  const loadAuditLogs = useCallback(async (workflowId = activeWorkflow.serverId, showNotice = true) => {
    if (!workflowId) {
      setAuditLogs([])
      if (showNotice) setNotice('当前工作流还没有同步到后端，暂无审计记录。')
      return []
    }
    setWorkflowMetaBusy('audit')
    try {
      const response = await apiFetch(`/api/audit-logs?resource_type=workflow&resource_id=${workflowId}`)
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, '读取审计记录失败。'))
      }
      const logs = (await response.json()) as AuditLogRecord[]
      setAuditLogs(logs)
      setBackendStatus('online')
      if (showNotice) setNotice(`已加载 ${logs.length} 条审计记录。`)
      return logs
    } catch (error) {
      const message = getErrorMessage(error, '读取审计记录失败：请确认后端在线。')
      setBackendStatus('offline')
      if (showNotice) setNotice(message)
      return []
    } finally {
      setWorkflowMetaBusy(null)
    }
  }, [activeWorkflow.serverId, apiFetch])

  const saveWorkflowVersion = async () => {
    if (!activeWorkflow.serverId) {
      setNotice('请先点击“同步到后端”，再保存版本。')
      return
    }
    if (activeWorkflowSyncState === 'dirty') {
      setNotice('当前工作流有未同步改动。请先同步到后端，再保存版本。')
      return
    }
    setWorkflowMetaBusy('save-version')
    try {
      const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}/versions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note: versionNote.trim() || null }),
      })
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, '保存版本失败。'))
      }
      const version = (await response.json()) as WorkflowVersionRecord
      setWorkflowVersions((current) => [version, ...current])
      setVersionNote('')
      setBackendStatus('online')
      setNotice(`已保存工作流版本 #${version.sequence}。`)
      void loadAuditLogs(activeWorkflow.serverId, false)
    } catch (error) {
      setBackendStatus('offline')
      setNotice(getErrorMessage(error, '保存版本失败：请确认后端在线。'))
    } finally {
      setWorkflowMetaBusy(null)
    }
  }

  const restoreWorkflowVersion = async (version: WorkflowVersionRecord) => {
    if (!activeWorkflow.serverId) return
    if (activeWorkflowSyncState === 'dirty') {
      setNotice('当前有未同步改动。请先同步或从后端加载后，再恢复版本。')
      return
    }
    const confirmed = window.confirm(`确认恢复到版本 #${version.sequence}？当前后端工作流会被替换，并生成新的恢复快照。`)
    if (!confirmed) return
    setWorkflowMetaBusy('restore')
    try {
      const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}/versions/${version.id}/restore`, {
        method: 'POST',
      })
      if (!response.ok) {
        throw new Error(await readResponseErrorMessage(response, '恢复版本失败。'))
      }
      const restored = (await response.json()) as ServerWorkflowRecord
      const syncedAt = new Date().toISOString()
      const restoredLocal = applyServerWorkflowToLocalRecord(activeWorkflow, restored, syncedAt)
      const next = {
        ...workflowStore,
        workflows: workflowStore.workflows.map((workflow) =>
          workflow.id === activeWorkflow.id ? restoredLocal : workflow,
        ),
      }
      setWorkflowStore(next)
      persistWorkflowStore(next)
      setSelectedNodeId(restored.nodes[0]?.id ?? '')
      setRunSteps([])
      setSelectedRunId('')
      setBackendStatus('online')
      setLastBackendSyncAt(syncedAt)
      setNotice(`已恢复到版本 #${version.sequence}。`)
      void loadWorkflowVersions(restored.id, false)
      void loadAuditLogs(restored.id, false)
    } catch (error) {
      setBackendStatus('offline')
      setNotice(getErrorMessage(error, '恢复版本失败：请确认后端在线。'))
    } finally {
      setWorkflowMetaBusy(null)
    }
  }

  const syncActiveWorkflowToBackend = async () => {
    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '同步')) return

    try {
      const syncedWorkflow = await syncWorkflowToBackend(activeWorkflow)
      const next = {
        ...workflowStore,
        workflows: workflowStore.workflows.map((workflow) =>
          workflow.id === activeWorkflow.id ? syncedWorkflow : workflow,
        ),
      }
      setWorkflowStore(next)
      persistWorkflowStore(next)
      setBackendStatus('online')
      setLastBackendSyncAt(syncedWorkflow.syncedAt ?? new Date().toISOString())
      setNotice('当前工作流已同步到后端。')
      if (syncedWorkflow.serverId) {
        void loadWorkflowVersions(syncedWorkflow.serverId, false)
        void loadAuditLogs(syncedWorkflow.serverId, false)
      }
    } catch (error) {
      if (error instanceof Error && error.message === 'remote_newer') {
        setBackendStatus('online')
        setNotice('后端版本比本地更新，已停止覆盖。请先点击“从后端加载”确认最新内容。')
        return
      }
      if (error instanceof Error && error.message === 'validation failed') return
      setBackendStatus('offline')
      setNotice('同步失败：后端不可用或请求失败。')
    }
  }

  const syncPendingWorkflowsToBackend = async () => {
    const pendingWorkflows = workflowStore.workflows.filter(
      (workflow) => !workflow.archived && getWorkflowSyncState(workflow) !== 'synced',
    )
    if (pendingWorkflows.length === 0) {
      setNotice('没有需要同步的未归档工作流。')
      return
    }

    const nextWorkflows = [...workflowStore.workflows]
    let syncedCount = 0
    let conflictCount = 0
    let failedCount = 0

    for (const workflow of pendingWorkflows) {
      const issues = validateWorkflow(workflow.nodes, workflow.edges)
      if (issues.some((issue) => issue.level === 'error')) {
        failedCount += 1
        continue
      }

      try {
        const syncedWorkflow = await syncWorkflowToBackend(workflow)
        const index = nextWorkflows.findIndex((item) => item.id === workflow.id)
        if (index >= 0) nextWorkflows[index] = syncedWorkflow
        syncedCount += 1
      } catch (error) {
        if (error instanceof Error && error.message === 'remote_newer') {
          conflictCount += 1
        } else {
          failedCount += 1
        }
      }
    }

    const next = {
      ...workflowStore,
      workflows: nextWorkflows,
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    const syncedAt = new Date().toISOString()
    setLastBackendSyncAt(syncedAt)
    setBackendStatus(failedCount > 0 ? 'offline' : 'online')
    setNotice(
      `批量同步完成：成功 ${syncedCount} 个，冲突 ${conflictCount} 个，失败 ${failedCount} 个。${
        conflictCount > 0 ? ' 有冲突的工作流请先从后端加载后再同步。' : ''
      }`,
    )
  }

  const refreshActiveWorkflowFromServerRecord = (serverWorkflow: ServerWorkflowRecord) => {
    const syncedAt = new Date().toISOString()
    const next = {
      ...workflowStore,
      workflows: workflowStore.workflows.map((workflow) =>
        workflow.id === activeWorkflow.id
          ? applyServerWorkflowToLocalRecord(workflow, serverWorkflow, syncedAt)
          : workflow,
      ),
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(serverWorkflow.nodes[0]?.id ?? '')
    setRunSteps([])
    setBackendStatus('online')
    setLastBackendSyncAt(syncedAt)
    void loadWorkflowVersions(serverWorkflow.id, false)
    void loadAuditLogs(serverWorkflow.id, false)
  }

  const ensureActiveWorkflowMatchesBackend = async () => {
    if (!activeWorkflow.serverId) return true
    const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}`)
    if (response.status === 404) {
      throw new Error('remote_missing')
    }
    if (!response.ok) {
      throw new Error('remote_check_failed')
    }
    const latest = (await response.json()) as ServerWorkflowRecord
    if (isServerWorkflowNewer(activeWorkflow, latest)) {
      refreshActiveWorkflowFromServerRecord(latest)
      throw new Error('remote_newer')
    }
    return true
  }

  const loadWorkflowsFromBackend = useCallback(async (mode: BackendWorkflowLoadMode = 'manual') => {
    try {
      const response = await apiFetch('/api/workflows')
      if (!response.ok) throw new Error('load failed')
      const serverWorkflows = (await response.json()) as ServerWorkflowRecord[]
      const imported = serverWorkflows.map(serverToWorkflowRecord)
      if (imported.length === 0) {
        setBackendStatus('online')
        if (mode === 'manual') {
          setNotice('后端在线，但还没有保存的工作流。')
        }
        return
      }
      const syncedAt = new Date().toISOString()
      const { store: next, firstLoaded, appendedCount, updatedCount, conflictCount } = mergeBackendWorkflows(
        workflowStore,
        imported,
        syncedAt,
      )
      setWorkflowStore(next)
      persistWorkflowStore(next)
      setSelectedNodeId(firstLoaded.nodes[0]?.id ?? '')
      setRunSteps([])
      setBackendStatus('online')
      setLastBackendSyncAt(syncedAt)
      if (firstLoaded.serverId) {
        void loadWorkflowVersions(firstLoaded.serverId, false)
        void loadAuditLogs(firstLoaded.serverId, false)
      }
      setNotice(
        mode === 'startup'
          ? `已自动从后端加载 ${imported.length} 个工作流：新增 ${appendedCount} 个，更新 ${updatedCount} 个，冲突保留 ${conflictCount} 个，本地未同步工作流已保留。`
          : `已从后端加载 ${imported.length} 个工作流：新增 ${appendedCount} 个，更新 ${updatedCount} 个，冲突保留 ${conflictCount} 个。`,
      )
    } catch {
      setBackendStatus('offline')
      if (mode === 'manual') {
        setNotice('加载失败：后端不可用或请求失败。')
      }
    }
  }, [apiFetch, loadAuditLogs, loadWorkflowVersions, workflowStore])

  useEffect(() => {
    if (!authSession) return
    const timer = window.setTimeout(() => {
      void loadWorkspaces()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [authSession, loadWorkspaces])

  useEffect(() => {
    if (!authSession || !activeWorkspaceId) return
    const timer = window.setTimeout(() => {
      void loadModelConfig(false)
      void loadAliyunConfig(false)
      void loadPaismartConfig(false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspaceId, authSession, loadAliyunConfig, loadModelConfig, loadPaismartConfig])

  useEffect(() => {
    if (!authSession || !activeWorkspaceId || adminView !== 'system') return
    const timer = window.setTimeout(() => {
      void loadAdminOverview(false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspaceId, adminView, authSession, loadAdminOverview])

  useEffect(() => {
    if (!authSession || !activeWorkspaceId) {
      const timer = window.setTimeout(() => {
        setWorkspaceMembers([])
      }, 0)
      return () => window.clearTimeout(timer)
    }
    const timer = window.setTimeout(() => {
      void loadWorkspaceMembers()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspaceId, authSession, loadWorkspaceMembers])

  useEffect(() => {
    if (!authSession || !activeWorkspaceId || activeWorkspace?.role !== 'owner') {
      const timer = window.setTimeout(() => {
        setWorkspaceInvitations([])
      }, 0)
      return () => window.clearTimeout(timer)
    }
    const timer = window.setTimeout(() => {
      void loadWorkspaceInvitations()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspace?.role, activeWorkspaceId, authSession, loadWorkspaceInvitations])

  useEffect(() => {
    if (!authSession || !activeWorkspaceId) return
    if (!activeWorkflow.serverId) return
    const timer = window.setTimeout(() => {
      void loadWorkflowVersions(activeWorkflow.serverId, false)
      void loadAuditLogs(activeWorkflow.serverId, false)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspaceId, activeWorkflow.serverId, authSession, loadAuditLogs, loadWorkflowVersions])

  useEffect(() => {
    if (!authSession) return
    if (didAutoLoadBackendRef.current) return
    if (!activeWorkspaceId) return
    didAutoLoadBackendRef.current = true
    const timer = window.setTimeout(() => {
      void loadWorkflowsFromBackend('startup')
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeWorkspaceId, authSession, loadWorkflowsFromBackend])

  const switchWorkspace = (workspaceId: string) => {
    setActiveWorkspaceId(workspaceId)
    persistActiveWorkspaceId(workspaceId)
    setKnowledgeStatus(null)
    setKnowledgeDocuments([])
    setModelConfig(null)
    setModelConfigForm(createDefaultProviderConfigForm('deepseek'))
    setAliyunConfig({
      record: null,
      form: createDefaultProviderConfigForm('aliyun'),
    })
    setPaismartConfig({
      record: null,
      form: { ...PAISMART_CONFIG_DEFAULTS },
    })
    setRunHistory([])
    setRunJobs([])
    setSelectedRunId('')
    setActiveRunJobId('')
    setRunSteps([])
    setWorkflowVersions([])
    setAuditLogs([])
    setVersionNote('')
    didAutoLoadBackendRef.current = false
    setNotice('已切换团队空间，请重新加载后端工作流和知识库状态。')
  }

  const runWorkflowOnBackend = async () => {
    if (!activeWorkflow.serverId) {
      setNotice('请先点击“同步到后端”，再使用后端运行。')
      return
    }
    if (activeWorkflowSyncState === 'dirty') {
      setNotice('当前工作流有未同步改动。请先点击“同步到后端”，再使用后端运行。')
      return
    }

    try {
      await ensureActiveWorkflowMatchesBackend()
    } catch (error) {
      if (error instanceof Error && error.message === 'remote_newer') {
        setNotice('后端版本已更新，已自动刷新当前工作流。请确认后再后端运行。')
        return
      }
      if (error instanceof Error && error.message === 'remote_missing') {
        setNotice('后端记录已不存在。请先点击“同步到后端”重新保存，再后端运行。')
        return
      }
      setBackendStatus('offline')
      setNotice('后端版本检查失败：请确认后端在线。')
      return
    }

    const status = await refreshProviderStatus(false)
    if (status && !deepseekConfigured && !status.openai_configured) {
      setNotice('未检测到 DeepSeek 或 OpenAI Key，大模型对话节点会使用模拟输出；阿里云多模态节点如已配置仍会真实调用。')
    }

    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '后端运行')) return

    try {
      const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}/runs`, {
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

  const pollRunJob = async (jobId: string) => {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      await new Promise((resolve) => window.setTimeout(resolve, 800))
      const response = await apiFetch(`/api/run-jobs/${jobId}`)
      if (!response.ok) throw new Error('poll job failed')
      const job = (await response.json()) as RunJobRecord
      setRunJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      if (job.status === 'succeeded' && job.run_id) {
        const runResponse = await apiFetch(`/api/runs/${job.run_id}`)
        if (!runResponse.ok) throw new Error('load job run failed')
        const run = (await runResponse.json()) as ServerRunRecord
        setRunSteps(run.steps)
        setRunHistory((current) => [run, ...current.filter((item) => item.id !== run.id)])
        setSelectedRunId(run.id)
        setBackendStatus('online')
        setNotice('异步运行已完成，结果已保存到运行历史。')
        return
      }
      if (job.status === 'failed') {
        setNotice(`异步运行失败：${job.error ?? '后端没有返回错误原因'}`)
        return
      }
      if (job.status === 'canceled') {
        setNotice('异步运行任务已取消。')
        return
      }
    }
    setNotice('异步运行仍在队列中，请稍后刷新运行任务。')
  }

  const runWorkflowAsyncOnBackend = async () => {
    if (!activeWorkflow.serverId) {
      setNotice('请先点击“同步到后端”，再使用异步运行。')
      return
    }
    if (activeWorkflowSyncState === 'dirty') {
      setNotice('当前工作流有未同步改动。请先同步到后端，再使用异步运行。')
      return
    }
    const issues = await validateActiveWorkflow()
    if (showBlockingIssues(issues, '异步运行')) return

    try {
      const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}/run-jobs`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ input_text: runInput }),
      })
      if (!response.ok) throw new Error('enqueue run failed')
      const job = (await response.json()) as RunJobRecord
      setRunJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      setActiveRunJobId(job.id)
      setBackendStatus('online')
      setNotice('已提交到异步运行队列，正在轮询结果。')
      void pollRunJob(job.id)
    } catch {
      setBackendStatus('offline')
      setNotice('提交异步运行失败：请确认后端在线，且当前空间有权限运行。')
    }
  }

  const loadRunJobs = async () => {
    if (!activeWorkflow.serverId) {
      setRunJobs([])
      return
    }
    try {
      const response = await apiFetch(`/api/run-jobs?workflow_id=${activeWorkflow.serverId}`)
      if (!response.ok) throw new Error('load jobs failed')
      const jobs = (await response.json()) as RunJobRecord[]
      setRunJobs(jobs)
      setBackendStatus('online')
      setNotice(`已加载 ${jobs.length} 条异步运行任务。`)
    } catch {
      setBackendStatus('offline')
      setNotice('加载异步运行任务失败：请确认后端在线。')
    }
  }

  const cancelRunJob = async (jobId: string) => {
    try {
      const response = await apiFetch(`/api/run-jobs/${jobId}/cancel`, { method: 'POST' })
      if (!response.ok) throw new Error('cancel job failed')
      const job = (await response.json()) as RunJobRecord
      setRunJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      setActiveRunJobId(job.id)
      setBackendStatus('online')
      setNotice('已取消排队中的异步任务。')
    } catch {
      setBackendStatus('offline')
      setNotice('取消异步任务失败：任务可能已经开始运行，请刷新队列查看最新状态。')
    }
  }

  const retryRunJob = async (jobId: string) => {
    try {
      const response = await apiFetch(`/api/run-jobs/${jobId}/retry`, { method: 'POST' })
      if (!response.ok) throw new Error('retry job failed')
      const job = (await response.json()) as RunJobRecord
      setRunJobs((current) => [job, ...current.filter((item) => item.id !== job.id)])
      setActiveRunJobId(job.id)
      setBackendStatus('online')
      setNotice('失败任务已重新入队，正在轮询结果。')
      void pollRunJob(job.id)
    } catch {
      setBackendStatus('offline')
      setNotice('重试异步任务失败：请确认后端在线，且任务状态仍为失败。')
    }
  }

  const clearTerminalRunJobs = async () => {
    if (!activeWorkflow.serverId) {
      setNotice('当前工作流还没有同步到后端，暂无可清理的队列任务。')
      return
    }
    try {
      const response = await apiFetch(`/api/run-jobs?workflow_id=${activeWorkflow.serverId}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('clear terminal jobs failed')
      setRunJobs((current) => current.filter((job) => !['succeeded', 'failed', 'canceled'].includes(job.status)))
      if (activeRunJob && ['succeeded', 'failed', 'canceled'].includes(activeRunJob.status)) {
        setActiveRunJobId('')
      }
      setBackendStatus('online')
      setNotice('已清理当前工作流已完成、失败和已取消的异步任务。')
    } catch {
      setBackendStatus('offline')
      setNotice('清理异步队列失败：请确认后端在线，且当前账号有编辑权限。')
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
      const response = await apiFetch(`/api/runs?workflow_id=${activeWorkflow.serverId}`)
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
      const response = await apiFetch(`/api/runs/${runId}`)
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
      const response = await apiFetch(`/api/runs/${runId}`, { method: 'DELETE' })
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
      const response = await apiFetch(`/api/runs?workflow_id=${activeWorkflow.serverId}`, {
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
    setSelectedRunId('')
    setWorkflowVersions([])
    setAuditLogs([])
    setVersionNote('')
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
      id: crypto.randomUUID(),
      name: `${activeWorkflow.name} 副本`,
      version: activeWorkflow.version,
      nodes: cloneNodes(activeWorkflow.nodes),
      edges: cloneEdges(activeWorkflow.edges),
      archived: false,
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

  const deleteWorkflow = async () => {
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

    if (activeWorkflow.serverId) {
      try {
        const response = await apiFetch(`/api/workflows/${activeWorkflow.serverId}`, {
          method: 'DELETE',
        })
        if (!response.ok && response.status !== 404) throw new Error('delete failed')
        setBackendStatus('online')
      } catch {
        setBackendStatus('offline')
        setNotice('删除失败：后端不可用或请求失败，本地工作流已保留。')
        return
      }
    }

    const next = {
      activeWorkflowId: nextActive.id,
      workflows: remaining,
    }
    setWorkflowStore(next)
    persistWorkflowStore(next)
    setSelectedNodeId(nextActive.nodes[0]?.id ?? '')
    setRunSteps([])
    setRunHistory([])
    setSelectedRunId('')
    setNotice(activeWorkflow.serverId ? '已删除当前工作流，并同步删除后端记录。' : '已删除当前本地工作流。')
  }

  const archiveActiveWorkflow = async () => {
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

    if (!toggledWorkflow?.serverId) return

    try {
      const response = await apiFetch(`/api/workflows/${toggledWorkflow.serverId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(workflowToServerPayload(toggledWorkflow)),
      })
      if (!response.ok) throw new Error('archive sync failed')
      const saved = (await response.json()) as ServerWorkflowRecord
      const syncedAt = new Date().toISOString()
      const syncedNext = {
        activeWorkflowId: next.activeWorkflowId,
        workflows: next.workflows.map((workflow) =>
          workflow.id === toggledWorkflow.id
            ? {
                ...workflow,
                archived: saved.archived ?? toggledWorkflow.archived,
                updatedAt: saved.updated_at,
                syncedAt,
              }
            : workflow,
        ),
      }
      setWorkflowStore(syncedNext)
      persistWorkflowStore(syncedNext)
      setBackendStatus('online')
      setLastBackendSyncAt(syncedAt)
    } catch {
      setBackendStatus('offline')
      setNotice(
        isArchiving
          ? '已在本地归档当前工作流，但后端归档状态同步失败。'
          : '已在本地恢复当前工作流，但后端归档状态同步失败。',
      )
    }
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

      if (data.kind === 'assign') {
        const output = renderTemplate(data.assignmentValue, context)
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: data.assignmentValue || '未配置赋值内容',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'template') {
        const output = renderTemplate(data.templateText, context)
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: data.templateText || '未配置模板',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'json') {
        const source = renderTemplate(data.jsonSource, context)
        try {
          const parsed = parseJsonPathValue(source, data.jsonPath ?? '')
          const output = formatWorkflowValue(parsed)
          steps.push({
            nodeId: node.id,
            title: `${index + 1}. ${data.label}`,
            status: 'done',
            input: `路径：${data.jsonPath || '(整个 JSON)'}\n${source}`,
            output,
            variable: writeOutput(output),
          })
        } catch (error) {
          steps.push({
            nodeId: node.id,
            title: `${index + 1}. ${data.label}`,
            status: 'error',
            input: source || '未配置 JSON 来源',
            output: 'JSON 解析失败。',
            error: getErrorMessage(error, 'JSON 解析失败'),
          })
        }
        return
      }

      if (data.kind === 'code') {
        try {
          const output = evaluateCodeExpression(data.codeExpression ?? '', context)
          steps.push({
            nodeId: node.id,
            title: `${index + 1}. ${data.label}`,
            status: 'done',
            input: data.codeExpression || '未配置表达式',
            output,
            variable: writeOutput(output),
          })
        } catch (error) {
          steps.push({
            nodeId: node.id,
            title: `${index + 1}. ${data.label}`,
            status: 'error',
            input: data.codeExpression || '未配置表达式',
            output: '代码表达式执行失败。',
            error: getErrorMessage(error, '代码表达式执行失败'),
          })
        }
        return
      }

      if (data.kind === 'loop') {
        const renderedItems = renderTemplate(data.loopItems, context)
        const items = parseLoopItems(renderedItems)
        const separator = data.loopSeparator ?? '\n'
        const output = items
          .map((item, itemIndex) =>
            renderTemplate(data.loopTemplate || '{{item}}', {
              ...context,
              item,
              index: String(itemIndex + 1),
            }),
          )
          .join(separator)
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: renderedItems || '未配置列表来源',
          output: output || '没有可迭代内容。',
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'aggregate') {
        const names = (data.aggregateVariables ?? '').split(/\r?\n|,/).map((item) => item.trim()).filter(Boolean)
        const output = names.map((name) => context[name] ?? '').filter(Boolean).join(data.aggregateSeparator ?? '\n\n')
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: names.join(', ') || '未配置聚合变量',
          output: output || '没有聚合到变量内容。',
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

      if (data.kind === 'tts') {
        const text = renderTemplate(data.ttsText, context)
        const output = `阿里云 TTS 模拟生成音频：${text.slice(0, 120)}`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: text || '未配置合成文本',
          output,
          variable: writeOutput(output),
          provider: `阿里云 TTS - ${data.ttsModel ?? 'cosyvoice-v2'}`,
        })
        return
      }

      if (data.kind === 'image') {
        const prompt = renderTemplate(data.imagePrompt, context)
        const output = `阿里云图片生成模拟输出 ${data.imageCount ?? 1} 张图：${prompt.slice(0, 120)}`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: prompt || '未配置图片提示词',
          output,
          variable: writeOutput(output),
          provider: `阿里云图片生成 - ${data.imageModel ?? 'wanx2.1-t2i-turbo'}`,
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

  if (!authSession) {
    return (
      <AuthView
        authMode={authMode}
        authNotice={authNotice}
        authPassword={authPassword}
        authUsername={authUsername}
        onPasswordChange={setAuthPassword}
        onSubmit={() => void handleAuthSubmit()}
        onUsernameChange={setAuthUsername}
        setAuthMode={setAuthMode}
      />
    )
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

        <section className="panel workspace-panel">
          <div className="panel-title between">
            <span>
              <Shield size={16} />
              团队空间
            </span>
            <button type="button" className="mini-action" onClick={() => void loadWorkspaces()}>
              刷新
            </button>
          </div>
          <select
            value={activeWorkspaceId}
            aria-label="当前团队空间"
            onChange={(event) => switchWorkspace(event.target.value)}
          >
            {workspaces.map((workspace) => (
              <option key={workspace.id} value={workspace.id}>
                {workspace.name}
              </option>
            ))}
          </select>
          <p className="workspace-role">
            {activeWorkspace ? `当前角色：${activeWorkspace.role}` : '暂未加载团队空间'}
          </p>
        </section>

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
              visibleWorkflows.map((workflow) => {
                const syncState = getWorkflowSyncState(workflow)
                return (
                  <button
                    key={workflow.id}
                    type="button"
                    className={clsx(
                      workflow.id === activeWorkflow.id && 'active',
                      workflow.archived && 'archived',
                      `sync-${syncState}`,
                    )}
                    onClick={() => switchWorkflow(workflow.id)}
                  >
                    <span>
                      {workflow.name}
                      {workflow.archived && <em>归档</em>}
                    </span>
                    <small>
                      <time>{new Date(workflow.updatedAt).toLocaleString('zh-CN')}</time>
                      <b className={clsx('workflow-sync-badge', syncState)}>{workflowSyncLabels[syncState]}</b>
                    </small>
                  </button>
                )
              })
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
              <span className={clsx('topbar-sync-state', activeWorkflowSyncState)}>
                {workflowSyncLabels[activeWorkflowSyncState]}
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
            <button type="button" className="ghost" onClick={syncPendingWorkflowsToBackend}>
              同步全部
            </button>
            <button type="button" className="ghost" onClick={() => loadWorkflowsFromBackend()}>
              从后端加载
            </button>
            <button type="button" className="ghost" onClick={logout}>
              退出 {authSession.user.username}
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
        <section className="panel admin-center-panel">
          <div className="panel-title">
            <Settings2 size={16} />
            <span>管理中心</span>
          </div>
          <div className="admin-tabs" role="tablist" aria-label="管理中心视图">
            {[
              ['node', '节点'],
              ['system', '系统'],
              ['team', '团队'],
              ['model', '模型'],
              ['knowledge', '知识库'],
              ['ops', '运维'],
              ['json', 'JSON'],
            ].map(([view, label]) => (
              <button
                key={view}
                type="button"
                className={clsx(adminView === view && 'active')}
                onClick={() => setAdminView(view as AdminView)}
              >
                {label}
              </button>
            ))}
          </div>
        </section>

        {adminView === 'system' && <section className="panel admin-overview-panel">
          <div className="panel-title between">
            <span>
              <TerminalSquare size={16} />
              系统概览
            </span>
            <button
              type="button"
              className="mini-action"
              disabled={adminOverviewBusy}
              onClick={() => void loadAdminOverview()}
            >
              {adminOverviewBusy ? '刷新中...' : '刷新'}
            </button>
          </div>
          {adminOverview ? (
            <>
              <div className="admin-overview-grid">
                <div>
                  <span>数据库</span>
                  <strong>{adminOverview.database}</strong>
                </div>
                <div>
                  <span>队列</span>
                  <strong>{adminOverview.queue_backend}</strong>
                </div>
                <div>
                  <span>成员</span>
                  <strong>{adminOverview.counts.members ?? 0}</strong>
                </div>
                <div>
                  <span>待用邀请</span>
                  <strong>{adminOverview.counts.pending_invitations ?? 0}</strong>
                </div>
                <div>
                  <span>工作流</span>
                  <strong>{adminOverview.counts.workflows ?? 0}</strong>
                </div>
                <div>
                  <span>运行记录</span>
                  <strong>{adminOverview.counts.runs ?? 0}</strong>
                </div>
                <div>
                  <span>排队任务</span>
                  <strong>{adminOverview.counts.queued_run_jobs ?? 0}</strong>
                </div>
                <div>
                  <span>失败任务</span>
                  <strong>{adminOverview.counts.failed_run_jobs ?? 0}</strong>
                </div>
                <div>
                  <span>成功率</span>
                  <strong>{adminOverview.run_metrics.success_rate}%</strong>
                </div>
                <div>
                  <span>平均耗时</span>
                  <strong>{adminOverview.run_metrics.average_duration_ms}ms</strong>
                </div>
                <div>
                  <span>平均节点</span>
                  <strong>{adminOverview.run_metrics.average_step_count}</strong>
                </div>
                <div>
                  <span>失败运行</span>
                  <strong>{adminOverview.run_metrics.error_runs}</strong>
                </div>
              </div>
              <div className="admin-overview-list">
                <article className="admin-health-row">
                  <strong>运行健康</strong>
                  <span>
                    最近 {adminOverview.run_metrics.sampled_runs} 次采样 ·
                    成功 {adminOverview.run_metrics.ok_runs} ·
                    失败 {adminOverview.run_metrics.error_runs}
                  </span>
                </article>
                <article>
                  <strong>模型与知识库</strong>
                  <span>
                    DeepSeek {adminOverview.provider_status.deepseek_configured ? '已配置' : '未配置'} ·
                    阿里云 {adminOverview.provider_status.aliyun_configured ? '已配置' : '未配置'} ·
                    知识文档 {adminOverview.knowledge_status.document_count}
                  </span>
                </article>
                <article>
                  <strong>当前空间</strong>
                  <span>{adminOverview.workspace.name} · {adminOverview.workspace.role}</span>
                </article>
                <article>
                  <strong>安全配置</strong>
                  <span>
                    登录 {adminOverview.settings.session_ttl_hours ?? '-'} 小时 ·
                    邀请 {adminOverview.settings.workspace_invitation_ttl_hours ?? '-'} 小时 ·
                    密钥保护 {adminOverview.settings.model_config_secret_configured ? '已启用' : '未启用'}
                  </span>
                </article>
                <article>
                  <strong>运行配置</strong>
                  <span>
                    {adminOverview.settings.app_env ?? 'development'} ·
                    Worker {adminOverview.settings.run_job_workers ?? 0} ·
                    RAG {adminOverview.settings.external_rag_enabled ? '已启用' : '未启用'}
                  </span>
                </article>
                <article>
                  <strong>访问来源</strong>
                  <span>{adminOverview.settings.cors_origins?.join(', ') || '未配置'}</span>
                </article>
                {adminOverview.recent_audit_logs.slice(0, 3).map((log) => (
                  <article key={log.id}>
                    <strong>{log.summary}</strong>
                    <span>{log.actor_username} · {new Date(log.created_at).toLocaleString('zh-CN')}</span>
                  </article>
                ))}
                {adminOverview.recent_run_jobs.slice(0, 3).map((job) => (
                  <article key={job.id}>
                    <strong>任务 {job.status}</strong>
                    <span>{new Date(job.updated_at).toLocaleString('zh-CN')}</span>
                  </article>
                ))}
                {adminOverview.run_metrics.recent_failed_runs.map((run) => (
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
        </section>}

        {adminView === 'node' && <section className="panel inspector">
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

          {selectedNode.data.kind === 'assign' && (
            <>
              <label>
                赋值内容
                <textarea
                  rows={4}
                  value={selectedNode.data.assignmentValue ?? ''}
                  onChange={(event) => updateSelectedNode({ assignmentValue: event.target.value })}
                />
                {renderFieldIssues('assignmentValue')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('assignmentValue', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'template' && (
            <>
              <label>
                文本模板
                <textarea
                  rows={6}
                  value={selectedNode.data.templateText ?? ''}
                  onChange={(event) => updateSelectedNode({ templateText: event.target.value })}
                />
                {renderFieldIssues('templateText')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('templateText', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'json' && (
            <>
              <label>
                JSON 来源
                <textarea
                  rows={5}
                  value={selectedNode.data.jsonSource ?? ''}
                  onChange={(event) => updateSelectedNode({ jsonSource: event.target.value })}
                />
                {renderFieldIssues('jsonSource')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('jsonSource', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
              <label>
                提取路径
                <input
                  value={selectedNode.data.jsonPath ?? ''}
                  onChange={(event) => updateSelectedNode({ jsonPath: event.target.value })}
                  placeholder="例如：items.0.title，留空返回整个 JSON"
                />
              </label>
            </>
          )}

          {selectedNode.data.kind === 'code' && (
            <>
              <label>
                受限表达式
                <textarea
                  rows={4}
                  value={selectedNode.data.codeExpression ?? ''}
                  onChange={(event) => updateSelectedNode({ codeExpression: event.target.value })}
                  placeholder="例如：upper(user_request)"
                />
                {renderFieldIssues('codeExpression')}
              </label>
              <p className="inspector-note">支持：upper(var)、lower(var)、trim(var)、length(var)，也支持直接写模板文本。</p>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('codeExpression', variable)}>
                    {variable}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'loop' && (
            <>
              <label>
                列表来源
                <textarea
                  rows={4}
                  value={selectedNode.data.loopItems ?? ''}
                  onChange={(event) => updateSelectedNode({ loopItems: event.target.value })}
                />
                {renderFieldIssues('loopItems')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('loopItems', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
              <label>
                单项模板
                <textarea
                  rows={3}
                  value={selectedNode.data.loopTemplate ?? ''}
                  onChange={(event) => updateSelectedNode({ loopTemplate: event.target.value })}
                />
              </label>
              <label>
                合并分隔符
                <input
                  value={selectedNode.data.loopSeparator ?? '\n'}
                  onChange={(event) => updateSelectedNode({ loopSeparator: event.target.value })}
                />
              </label>
            </>
          )}

          {selectedNode.data.kind === 'aggregate' && (
            <>
              <label>
                要聚合的变量名
                <textarea
                  rows={4}
                  value={selectedNode.data.aggregateVariables ?? ''}
                  onChange={(event) => updateSelectedNode({ aggregateVariables: event.target.value })}
                  placeholder={'draft\nloop_result'}
                />
                {renderFieldIssues('aggregateVariables')}
              </label>
              <label>
                合并分隔符
                <input
                  value={selectedNode.data.aggregateSeparator ?? '\n\n'}
                  onChange={(event) => updateSelectedNode({ aggregateSeparator: event.target.value })}
                />
              </label>
            </>
          )}

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
                知识来源
                <select
                  value={selectedNode.data.knowledgeProvider ?? 'local'}
                  onChange={(event) => updateSelectedNode({ knowledgeProvider: event.target.value as KnowledgeProvider })}
                >
                  <option value="local">本地知识库</option>
                  <option value="paismart">PaiSmart RAG</option>
                </select>
              </label>
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

          {selectedNode.data.kind === 'tts' && (
            <>
              <label>
                阿里云 TTS 模型
                <input
                  value={selectedNode.data.ttsModel ?? 'cosyvoice-v2'}
                  onChange={(event) => updateSelectedNode({ ttsModel: event.target.value })}
                />
              </label>
              <div className="tts-voice-panel">
                <label>
                  常用音色
                  <select
                    value={
                      ttsVoiceOptions.some((option) => option.value === (selectedNode.data.ttsVoice ?? 'longxiaochun_v2'))
                        ? selectedNode.data.ttsVoice ?? 'longxiaochun_v2'
                        : 'custom'
                    }
                    onChange={(event) => {
                      if (event.target.value !== 'custom') {
                        updateSelectedNode({ ttsVoice: event.target.value })
                      }
                    }}
                  >
                    {ttsVoiceOptions.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                    <option value="custom">自定义音色</option>
                  </select>
                </label>
                <label>
                  音色代码
                  <input
                    value={selectedNode.data.ttsVoice ?? 'longxiaochun_v2'}
                    onChange={(event) => updateSelectedNode({ ttsVoice: event.target.value })}
                    placeholder="例如：longxiaochun_v2"
                  />
                </label>
              </div>
              <div className="tts-params-grid">
                <label>
                  音频格式
                  <select
                    value={selectedNode.data.audioFormat ?? 'mp3'}
                    onChange={(event) => updateSelectedNode({ audioFormat: event.target.value as 'mp3' | 'wav' })}
                  >
                    <option value="mp3">mp3</option>
                    <option value="wav">wav</option>
                  </select>
                </label>
                <div className="speech-rate-control">
                  <span>语速</span>
                  <div>
                    <input
                      aria-label="TTS 语速滑块"
                      min={0.5}
                      max={2}
                      step={0.1}
                      type="range"
                      value={selectedNode.data.speechRate ?? 1}
                      onChange={(event) => updateSelectedNode({ speechRate: Number(event.target.value) })}
                    />
                    <input
                      aria-label="TTS 语速数值"
                      min={0.5}
                      max={2}
                      step={0.1}
                      type="number"
                      value={selectedNode.data.speechRate ?? 1}
                      onChange={(event) => updateSelectedNode({ speechRate: Number(event.target.value) })}
                    />
                  </div>
                  <small>0.5 慢速，1.0 正常，2.0 快速</small>
                  {renderFieldIssues('speechRate')}
                </div>
              </div>
              <label>
                合成文本
                <textarea
                  rows={5}
                  value={selectedNode.data.ttsText ?? ''}
                  onChange={(event) => updateSelectedNode({ ttsText: event.target.value })}
                />
                {renderFieldIssues('ttsText')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('ttsText', variable)}>
                    {`{{${variable}}}`}
                  </button>
                ))}
              </div>
            </>
          )}

          {selectedNode.data.kind === 'image' && (
            <>
              <label>
                阿里云图片模型
                <input
                  value={selectedNode.data.imageModel ?? 'wanx2.1-t2i-turbo'}
                  onChange={(event) => updateSelectedNode({ imageModel: event.target.value })}
                />
              </label>
              <div className="llm-params-grid">
                <label>
                  图片尺寸
                  <select
                    value={selectedNode.data.imageSize ?? '1024*1024'}
                    onChange={(event) => updateSelectedNode({ imageSize: event.target.value })}
                  >
                    <option value="1024*1024">1024*1024</option>
                    <option value="768*1024">768*1024</option>
                    <option value="1024*768">1024*768</option>
                    <option value="720*1280">720*1280</option>
                    <option value="1280*720">1280*720</option>
                  </select>
                </label>
                <label>
                  生成数量
                  <input
                    min={1}
                    max={4}
                    type="number"
                    value={selectedNode.data.imageCount ?? 1}
                    onChange={(event) => updateSelectedNode({ imageCount: Number(event.target.value) })}
                  />
                  {renderFieldIssues('imageCount')}
                </label>
              </div>
              <label>
                图片提示词
                <textarea
                  rows={5}
                  value={selectedNode.data.imagePrompt ?? ''}
                  onChange={(event) => updateSelectedNode({ imagePrompt: event.target.value })}
                />
                {renderFieldIssues('imagePrompt')}
              </label>
              <div className="insert-row">
                {variableKeys.map((variable) => (
                  <button key={variable} type="button" onClick={() => appendToSelectedField('imagePrompt', variable)}>
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
        </section>}

        {adminView === 'team' && <section className="panel workspace-admin-panel">
          <div className="panel-title between">
            <span>
              <Shield size={16} />
              团队成员
            </span>
            <button
              type="button"
              className="mini-action"
              disabled={Boolean(workspaceMemberBusy)}
              onClick={() => void loadWorkspaceMembers()}
            >
              {workspaceMemberBusy === 'load' ? '读取中...' : '刷新'}
            </button>
          </div>
          <div className="workspace-member-list">
            {workspaceMembers.length === 0 ? (
              <p>暂无成员信息。</p>
            ) : (
              workspaceMembers.map((member) => (
                <article key={member.id}>
                  <div>
                    <strong>{member.username}</strong>
                    <small>{member.id === authSession.user.id ? '当前账号' : new Date(member.created_at).toLocaleString('zh-CN')}</small>
                  </div>
                  {activeWorkspace?.role === 'owner' ? (
                    <div className="workspace-member-actions">
                      <select
                        aria-label={`设置 ${member.username} 的角色`}
                        value={member.role}
                        disabled={workspaceMemberBusy === 'role'}
                        onChange={(event) =>
                          void updateWorkspaceMemberRole(member, event.target.value as WorkspaceRecord['role'])
                        }
                      >
                        <option value="viewer">viewer</option>
                        <option value="editor">editor</option>
                        <option value="owner">owner</option>
                      </select>
                      <button
                        type="button"
                        disabled={member.id === authSession.user.id || workspaceMemberBusy === 'remove'}
                        onClick={() => void removeWorkspaceMember(member)}
                      >
                        移除
                      </button>
                    </div>
                  ) : (
                    <span className="workspace-role-pill">{member.role}</span>
                  )}
                </article>
              ))
            )}
          </div>
          <div className="panel-title between workspace-subtitle">
            <span>团队邀请</span>
            {activeWorkspace?.role === 'owner' && (
              <button
                type="button"
                className="mini-action"
                disabled={Boolean(workspaceInviteBusy)}
                onClick={() => void loadWorkspaceInvitations()}
              >
                {workspaceInviteBusy === 'load' ? '读取中...' : '刷新邀请'}
              </button>
            )}
          </div>
          <div className="workspace-join-form">
            <input
              value={invitationCodeInput}
              onChange={(event) => setInvitationCodeInput(event.target.value)}
              placeholder="输入别人发给你的邀请码"
            />
            <button
              type="button"
              className="mini-action"
              disabled={workspaceInviteBusy === 'accept'}
              onClick={() => void acceptWorkspaceInvitation()}
            >
              {workspaceInviteBusy === 'accept' ? '加入中...' : '加入团队'}
            </button>
          </div>
          {activeWorkspace?.role === 'owner' ? (
            <>
              <div className="workspace-invite-create">
                <select
                  aria-label="邀请角色"
                  value={invitationRole}
                  onChange={(event) => setInvitationRole(event.target.value as WorkspaceRecord['role'])}
                >
                  <option value="viewer">viewer 可查看和运行</option>
                  <option value="editor">editor 可编辑</option>
                  <option value="owner">owner 可管理成员</option>
                </select>
                <button
                  type="button"
                  className="mini-action"
                  disabled={workspaceInviteBusy === 'create'}
                  onClick={() => void createWorkspaceInvitation()}
                >
                  {workspaceInviteBusy === 'create' ? '创建中...' : '创建邀请码'}
                </button>
              </div>
              <div className="workspace-invitation-list">
                {workspaceInvitations.length === 0 ? (
                  <p>暂无邀请记录。</p>
                ) : (
                  workspaceInvitations.slice(0, 5).map((invitation) => (
                    <article key={invitation.id}>
                      <div>
                        <strong>{invitation.role} · {invitationStatusLabel(invitation)}</strong>
                        <code>{invitation.code}</code>
                        <small>
                          {invitation.accepted_by_username
                            ? `已由 ${invitation.accepted_by_username} 接受`
                            : `有效至 ${new Date(invitation.expires_at).toLocaleString('zh-CN')}`}
                        </small>
                      </div>
                      <div className="workspace-invitation-actions">
                        <button type="button" onClick={() => copyText('邀请码', invitation.code)}>
                          复制
                        </button>
                        <button
                          type="button"
                          disabled={!canRevokeInvitation(invitation) || workspaceInviteBusy === 'revoke'}
                          onClick={() => void revokeWorkspaceInvitation(invitation.id)}
                        >
                          撤销
                        </button>
                      </div>
                    </article>
                  ))
                )}
              </div>
            </>
          ) : (
            <p className="model-status-note">当前角色不是 owner，只能使用邀请码加入其他团队空间。</p>
          )}
        </section>}

        {adminView === 'model' && <section className="panel model-status-panel">
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
              <strong className={clsx(deepseekConfigured ? 'ready' : 'fallback')}>
                {deepseekConfigured ? '已配置' : '未配置'}
              </strong>
            </div>
            <div>
              <span>默认模型</span>
              <strong>{modelConfig?.model ?? providerStatus?.deepseek_model ?? '未读取'}</strong>
            </div>
            <div>
              <span>OpenAI</span>
              <strong className={clsx(providerStatus?.openai_configured ? 'ready' : 'fallback')}>
                {providerStatus?.openai_configured ? '已配置' : '未配置'}
              </strong>
            </div>
            <div>
              <span>阿里云多模态</span>
              <strong className={clsx(aliyunConfigured ? 'ready' : 'fallback')}>
                {aliyunConfigured ? '已配置' : '未配置'}
              </strong>
            </div>
            <div>
              <span>阿里云模型</span>
              <strong>{aliyunConfig.record?.model ?? providerStatus?.aliyun_tts_model ?? '未读取'}</strong>
            </div>
            <div>
              <span>后端状态</span>
              <strong>{backendStatus === 'online' ? '在线' : backendStatus === 'offline' ? '离线' : '未检查'}</strong>
            </div>
            <div>
              <span>PaiSmart RAG</span>
              <strong className={clsx(providerStatus?.external_rag_enabled || paismartWorkspaceConfigured ? 'ready' : 'fallback')}>
                {providerStatus?.external_rag_enabled || paismartWorkspaceConfigured ? '已启用' : '未启用'}
              </strong>
            </div>
            <div>
              <span>RAG 地址</span>
              <strong>{paismartConfig.record?.base_url ?? providerStatus?.external_rag_base_url ?? '未读取'}</strong>
            </div>
          </div>
          <p className="model-status-note">
            {hasRealModelProvider ? '后端运行会优先使用真实模型。' : '未配置模型 Key 时，后端运行会自动使用模拟输出。'}
          </p>
          <div className="model-config-form">
            <div className="model-config-block">
              <div className="model-config-heading">
                <strong>DeepSeek 大模型</strong>
                <span>用于大模型对话节点</span>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={modelConfigForm.enabled}
                  onChange={(event) => updateModelConfigForm({ enabled: event.target.checked })}
                />
                启用团队空间 DeepSeek
              </label>
              <label>
                模型
                <input
                  value={modelConfigForm.model}
                  onChange={(event) => updateModelConfigForm({ model: event.target.value })}
                  placeholder="deepseek-v4-flash"
                />
              </label>
              <label>
                Base URL
                <input
                  value={modelConfigForm.baseUrl}
                  onChange={(event) => updateModelConfigForm({ baseUrl: event.target.value })}
                  placeholder="https://api.deepseek.com"
                />
              </label>
              <label>
                API Key
                <input
                  type="password"
                  value={modelConfigForm.apiKey}
                  onChange={(event) => updateModelConfigForm({ apiKey: event.target.value })}
                  placeholder={modelConfig?.masked_api_key ?? '首次保存需要填写'}
                />
              </label>
              <div className="model-config-actions">
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void saveModelConfig()}
                >
                  {modelConfigBusy === 'save' && modelConfigFeedback?.provider === 'deepseek' ? '保存中...' : '保存配置'}
                </button>
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void testModelConfig()}
                >
                  {modelConfigBusy === 'test' && modelConfigFeedback?.provider === 'deepseek' ? '测试中...' : '测试配置'}
                </button>
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void loadModelConfig(true)}
                >
                  {modelConfigBusy === 'load' && modelConfigFeedback?.provider === 'deepseek' ? '读取中...' : '重新读取'}
                </button>
              </div>
              {modelConfigFeedback?.provider === 'deepseek' && (
                <p className={clsx('model-config-feedback', modelConfigFeedback.type)}>
                  {modelConfigFeedback.text}
                </p>
              )}
              <p className="model-status-note">
                {modelConfig?.has_api_key
                  ? `当前团队空间已保存 Key：${modelConfig.masked_api_key ?? '******'}`
                  : '当前团队空间还没有保存 DeepSeek Key。'}
              </p>
            </div>

            <div className="model-config-block">
              <div className="model-config-heading">
                <strong>阿里云百炼</strong>
                <span>用于文字转语音和图片生成节点</span>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={aliyunConfig.form.enabled}
                  onChange={(event) => updateAliyunConfigForm({ enabled: event.target.checked })}
                />
                启用团队空间阿里云百炼
              </label>
              <label>
                默认 TTS 模型
                <input
                  value={aliyunConfig.form.model}
                  onChange={(event) => updateAliyunConfigForm({ model: event.target.value })}
                  placeholder="cosyvoice-v2"
                />
              </label>
              <label>
                Base URL
                <input
                  value={aliyunConfig.form.baseUrl}
                  onChange={(event) => updateAliyunConfigForm({ baseUrl: event.target.value })}
                  placeholder="https://dashscope.aliyuncs.com"
                />
              </label>
              <label>
                API Key
                <input
                  type="password"
                  value={aliyunConfig.form.apiKey}
                  onChange={(event) => updateAliyunConfigForm({ apiKey: event.target.value })}
                  placeholder={aliyunConfig.record?.masked_api_key ?? '首次保存需要填写'}
                />
              </label>
              <div className="model-config-actions">
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void saveAliyunConfig()}
                >
                  {modelConfigBusy === 'save' && modelConfigFeedback?.provider === 'aliyun' ? '保存中...' : '保存配置'}
                </button>
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void testAliyunConfig()}
                >
                  {modelConfigBusy === 'test' && modelConfigFeedback?.provider === 'aliyun' ? '测试中...' : '测试配置'}
                </button>
                <button
                  type="button"
                  className="mini-action"
                  disabled={Boolean(modelConfigBusy)}
                  onClick={() => void loadAliyunConfig(true)}
                >
                  {modelConfigBusy === 'load' && modelConfigFeedback?.provider === 'aliyun' ? '读取中...' : '重新读取'}
                </button>
              </div>
              {modelConfigFeedback?.provider === 'aliyun' && (
                <p className={clsx('model-config-feedback', modelConfigFeedback.type)}>
                  {modelConfigFeedback.text}
                </p>
              )}
              <p className="model-status-note">
                {aliyunConfig.record?.has_api_key
                  ? `当前团队空间已保存 Key：${aliyunConfig.record.masked_api_key ?? '******'}`
                  : '当前团队空间还没有保存阿里云百炼 Key。'}
              </p>
              <p className="model-status-note">保存后，文字转语音和图片生成节点会优先使用当前团队空间配置。</p>
            </div>
            <div className="model-config-block">
              <div className="model-config-heading">
                <strong>PaiSmart RAG</strong>
                <span>用于知识检索节点的外部 RAG 服务</span>
              </div>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={paismartConfig.form.enabled}
                  onChange={(event) => updatePaismartConfigForm({ enabled: event.target.checked })}
                />
                启用团队空间 PaiSmart
              </label>
              <label>
                检索模式
                <input
                  value={paismartConfig.form.model}
                  onChange={(event) => updatePaismartConfigForm({ model: event.target.value })}
                  placeholder="hybrid"
                />
              </label>
              <label>
                Base URL
                <input
                  value={paismartConfig.form.baseUrl}
                  onChange={(event) => updatePaismartConfigForm({ baseUrl: event.target.value })}
                  placeholder="http://127.0.0.1:8080"
                />
              </label>
              <label>
                Token
                <input
                  type="password"
                  value={paismartConfig.form.apiKey}
                  onChange={(event) => updatePaismartConfigForm({ apiKey: event.target.value })}
                  placeholder={paismartConfig.record?.masked_api_key ?? '首次保存需要填写；无 Token 可填 none'}
                />
              </label>
              <div className="model-config-actions">
                <button type="button" className="mini-action" disabled={Boolean(modelConfigBusy)} onClick={() => void savePaismartConfig()}>
                  {modelConfigBusy === 'save' && modelConfigFeedback?.provider === 'paismart' ? '保存中...' : '保存配置'}
                </button>
                <button type="button" className="mini-action" disabled={Boolean(modelConfigBusy)} onClick={() => void testPaismartConfig()}>
                  {modelConfigBusy === 'test' && modelConfigFeedback?.provider === 'paismart' ? '测试中...' : '测试配置'}
                </button>
                <button type="button" className="mini-action" disabled={Boolean(modelConfigBusy)} onClick={() => void loadPaismartConfig(true)}>
                  {modelConfigBusy === 'load' && modelConfigFeedback?.provider === 'paismart' ? '读取中...' : '重新读取'}
                </button>
              </div>
              {modelConfigFeedback?.provider === 'paismart' && (
                <p className={clsx('model-config-feedback', modelConfigFeedback.type)}>
                  {modelConfigFeedback.text}
                </p>
              )}
              <p className="model-status-note">
                {paismartConfig.record?.has_api_key
                  ? `当前团队空间已保存 Token：${paismartConfig.record.masked_api_key ?? '******'}`
                  : '当前团队空间还没有保存 PaiSmart Token。'}
              </p>
              <p className="model-status-note">知识检索节点选择 PaiSmart RAG 时，会优先使用当前团队空间配置。</p>
            </div>
          </div>
          {providerStatusCheckedAt && (
            <time className="model-status-time">
              更新：{new Date(providerStatusCheckedAt).toLocaleString('zh-CN')}
            </time>
          )}
        </section>}

        {adminView === 'knowledge' && <section className="panel knowledge-status-panel">
          <div className="panel-title between">
            <span>
              <Search size={16} />
              知识库
            </span>
            <div className="knowledge-actions">
              <input
                ref={knowledgeFileInputRef}
                type="file"
                accept=".md,.txt,text/markdown,text/plain"
                className="file-input"
                onChange={uploadKnowledgeDocument}
              />
              <button type="button" className="mini-action" onClick={() => knowledgeFileInputRef.current?.click()}>
                上传
              </button>
              <button type="button" className="mini-action" onClick={() => refreshKnowledgeStatus()}>
                刷新
              </button>
            </div>
          </div>
          <div className="model-status-current">
            <span className={clsx('model-status-dot', knowledgeStatus?.document_count ? 'ready' : 'fallback')} />
            <strong>{knowledgeStatusLabel}</strong>
          </div>
          <p className="model-status-note">
            知识检索节点会读取后端本地 knowledge 目录中的 Markdown 和 TXT 文档。
          </p>
          <div className="knowledge-document-list">
            {knowledgeDocuments.length === 0 ? (
              <p>暂无已加载文档。</p>
            ) : (
              knowledgeDocuments.map((document) => (
                <div key={document.name}>
                  <span>
                    <strong>{document.name}</strong>
                    <small>
                      {document.chunk_count} 个片段 · {Math.max(1, Math.round(document.size / 1024))} KB
                    </small>
                  </span>
                  <button type="button" aria-label={`删除 ${document.name}`} onClick={() => deleteKnowledgeDocument(document.name)}>
                    <Trash2 size={13} />
                  </button>
                </div>
              ))
            )}
          </div>
          {knowledgeStatus && <time className="model-status-time">{knowledgeStatus.directory}</time>}
        </section>}

        {adminView === 'ops' && <section className="panel workflow-meta-panel">
          <div className="panel-title between">
            <span>
              <Archive size={16} />
              版本与审计
            </span>
            <div className="workflow-meta-actions">
              <button
                type="button"
                className="mini-action"
                disabled={!activeWorkflow.serverId || Boolean(workflowMetaBusy)}
                onClick={() => void loadWorkflowVersions()}
              >
                {workflowMetaBusy === 'versions' ? '刷新中...' : '版本'}
              </button>
              <button
                type="button"
                className="mini-action"
                disabled={!activeWorkflow.serverId || Boolean(workflowMetaBusy)}
                onClick={() => void loadAuditLogs()}
              >
                {workflowMetaBusy === 'audit' ? '刷新中...' : '审计'}
              </button>
            </div>
          </div>
          {!activeWorkflow.serverId ? (
            <p className="model-status-note">当前工作流还没有同步到后端，暂无版本历史和审计记录。</p>
          ) : (
            <>
              <label className="version-note-input">
                版本备注
                <input
                  value={versionNote}
                  onChange={(event) => setVersionNote(event.target.value)}
                  placeholder="例如：面试演示稳定版"
                />
              </label>
              <button
                type="button"
                className="workflow-version-save"
                disabled={Boolean(workflowMetaBusy) || activeWorkflowSyncState === 'dirty'}
                onClick={() => void saveWorkflowVersion()}
              >
                {workflowMetaBusy === 'save-version' ? '保存中...' : '保存当前版本'}
              </button>
              <div className="workflow-version-list">
                {workflowVersions.length === 0 ? (
                  <p>暂无版本记录。</p>
                ) : (
                  workflowVersions.slice(0, 5).map((version) => (
                    <article key={version.id}>
                      <div>
                        <strong>版本 #{version.sequence}</strong>
                        <span>{new Date(version.created_at).toLocaleString('zh-CN')}</span>
                        <small>{version.note || version.name}</small>
                      </div>
                      <button
                        type="button"
                        disabled={Boolean(workflowMetaBusy) || activeWorkflowSyncState === 'dirty'}
                        onClick={() => void restoreWorkflowVersion(version)}
                      >
                        恢复
                      </button>
                    </article>
                  ))
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
        </section>}

        {adminView === 'ops' && <section className="panel runner">
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
              同步运行
            </button>
            <button type="button" onClick={runWorkflowAsyncOnBackend}>
              异步入队
            </button>
            <button type="button" onClick={loadRunHistory}>
              加载历史
            </button>
            <button type="button" onClick={loadRunJobs}>
              刷新队列
            </button>
            <button type="button" onClick={clearTerminalRunJobs}>
              清理队列
            </button>
            <button type="button" onClick={clearCurrentRunHistory}>
              清空历史
            </button>
          </div>

          <div className="run-job-strip">
            {activeRunJob ? (
              <span>
                当前任务：{runJobStatusLabels[activeRunJob.status]}
                {activeRunJob.run_id ? ` · 运行记录 ${activeRunJob.run_id.slice(0, 8)}` : ''}
              </span>
            ) : (
              <span>异步队列空闲</span>
            )}
            {runJobs.slice(0, 3).map((job) => (
              <div key={job.id} className="run-job-item">
                <button type="button" onClick={() => setActiveRunJobId(job.id)}>
                  {runJobStatusLabels[job.status]}
                </button>
                {job.status === 'queued' ? (
                  <button type="button" onClick={() => void cancelRunJob(job.id)}>
                    取消
                  </button>
                ) : null}
                {job.status === 'failed' ? (
                  <button type="button" onClick={() => void retryRunJob(job.id)}>
                    重试
                  </button>
                ) : null}
              </div>
            ))}
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
                {runSteps.map((step) => {
                  const stepId = step.nodeId ?? step.node_id ?? step.title
                  const outputUrl = extractFirstUrl(step.output)
                  const audioUrl = outputUrl && isAudioStep(step) ? outputUrl : ''
                  const simulatedAudio = !audioUrl && isSimulatedAudioStep(step)
                  return (
                    <article key={stepId}>
                      <span className={clsx('status-dot', step.status)} />
                      <div>
                        <strong>{step.title}</strong>
                        <div className="run-step-meta">
                          <span>耗时 {step.duration_ms ?? 0}ms</span>
                          <span>尝试 {step.attempt_count ?? 1} 次</span>
                        </div>
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
                                  <button type="button" onClick={() => copyText('音频链接', audioUrl)}>
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
                  )
                })}
              </>
            )}
          </div>
        </section>}

        {adminView === 'json' && <section className="panel json-panel">
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
        </section>}
      </aside>
    </main>
  )
}

export default App
