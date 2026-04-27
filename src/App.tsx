import { useCallback, useMemo, useRef, useState, type ChangeEvent } from 'react'
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
  Bot,
  Braces,
  ChevronRight,
  CircleDot,
  Code2,
  Download,
  GitBranch,
  ListChecks,
  MessageSquareText,
  Play,
  Plus,
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

type WorkflowNodeData = {
  kind: NodeKind
  label: string
  description: string
  model?: string
  prompt?: string
  query?: string
  toolName?: string
  condition?: string
  outputKey?: string
}

type WorkflowNode = Node<WorkflowNodeData, 'workflow'>

type RunStep = {
  nodeId: string
  title: string
  status: 'done' | 'routed' | 'waiting' | 'skipped' | 'error'
  input: string
  output: string
  variable?: string
}

type WorkflowDefinition = {
  name: string
  version: string
  nodes: WorkflowNode[]
  edges: Edge[]
  updatedAt?: string
}

const STORAGE_KEY = 'workflow-studio.current-workflow'

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
      toolName: 'webhook.lookup',
      outputKey: 'tool_result',
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

const examples = [
  '总结用户反馈，并生成按优先级排序的产品行动项。',
  '根据 CRM 数据和品牌语气，撰写一封新用户欢迎邮件。',
  '检查客服工单，判断紧急程度，并起草回复。',
]

const createWorkflowDefinition = (
  nodes: WorkflowNode[],
  edges: Edge[],
  updatedAt?: string,
): WorkflowDefinition => ({
  name: '工作流编辑器演示',
  version: '0.2.0',
  nodes,
  edges,
  updatedAt,
})

const isWorkflowDefinition = (value: unknown): value is WorkflowDefinition => {
  if (!value || typeof value !== 'object') return false
  const candidate = value as Partial<WorkflowDefinition>
  return Array.isArray(candidate.nodes) && Array.isArray(candidate.edges)
}

const loadStoredWorkflow = (): WorkflowDefinition | null => {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw) as unknown
    return isWorkflowDefinition(parsed) ? parsed : null
  } catch {
    return null
  }
}

const renderTemplate = (template: string | undefined, context: Record<string, string>) =>
  (template ?? '').replace(/\{\{\s*([\w.-]+)\s*\}\}/g, (_, key: string) => context[key] ?? '')

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

function WorkflowNodeCard({ data, selected }: NodeProps<WorkflowNode>) {
  const meta = nodeMeta[data.kind]
  const Icon = meta.icon

  return (
    <div className={clsx('workflow-node', selected && 'selected')}>
      <Handle type="target" position={Position.Left} />
      <div className="node-head">
        <span className="node-icon" style={{ color: meta.color, backgroundColor: `${meta.color}16` }}>
          <Icon size={17} />
        </span>
        <div>
          <strong>{data.label}</strong>
          <small>{meta.title}</small>
        </div>
      </div>
      <p>{data.description}</p>
      <div className="node-vars">
        {data.model && <span>{data.model}</span>}
        {data.toolName && <span>{data.toolName}</span>}
        {data.outputKey && <span>{`{{${data.outputKey}}}`}</span>}
      </div>
      <Handle type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { workflow: WorkflowNodeCard }

function App() {
  const storedWorkflow = useMemo(() => loadStoredWorkflow(), [])
  const [nodes, setNodes] = useState<WorkflowNode[]>(storedWorkflow?.nodes ?? initialNodes)
  const [edges, setEdges] = useState<Edge[]>(storedWorkflow?.edges ?? initialEdges)
  const [selectedNodeId, setSelectedNodeId] = useState('llm-1')
  const [runSteps, setRunSteps] = useState<RunStep[]>([])
  const [activeExample, setActiveExample] = useState(examples[0])
  const [lastSavedAt, setLastSavedAt] = useState(storedWorkflow?.updatedAt ?? '')
  const [notice, setNotice] = useState(storedWorkflow ? '已从本地恢复上次编辑的工作流。' : '')
  const nextNodeId = useRef(1)
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0]

  const variables = useMemo(
    () =>
      nodes
        .map((node) => node.data.outputKey)
        .filter((key): key is string => Boolean(key))
        .map((key) => `{{${key}}}`),
    [nodes],
  )

  const onNodesChange = useCallback((changes: NodeChange<WorkflowNode>[]) => {
    setNodes((current) => applyNodeChanges(changes, current))
    setNotice('')
  }, [])

  const onEdgesChange = useCallback((changes: EdgeChange[]) => {
    setEdges((current) => applyEdgeChanges(changes, current))
    setNotice('')
  }, [])

  const onConnect = useCallback((connection: Connection) => {
    setEdges((current) =>
      addEdge({ ...connection, animated: connection.source === 'input-1' }, current),
    )
    setNotice('')
  }, [])

  const updateSelectedNode = (patch: Partial<WorkflowNodeData>) => {
    setNodes((current) =>
      current.map((node) =>
        node.id === selectedNode.id ? { ...node, data: { ...node.data, ...patch } } : node,
      ),
    )
    setNotice('')
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

    setNodes((current) => [...current, node])
    setSelectedNodeId(id)
    setRunSteps([])
    setNotice('')
  }

  const deleteSelectedNode = () => {
    if (!selectedNode || selectedNode.data.kind === 'input') return
    setNodes((current) => current.filter((node) => node.id !== selectedNode.id))
    setEdges((current) =>
      current.filter((edge) => edge.source !== selectedNode.id && edge.target !== selectedNode.id),
    )
    setSelectedNodeId(nodes[0]?.id ?? '')
    setRunSteps([])
    setNotice('')
  }

  const runWorkflow = () => {
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
      return
    }

    const context: Record<string, string> = {}
    const steps: RunStep[] = []
    let branchOpen = true

    order.forEach((node, index) => {
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
        const output = activeExample
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: '运行示例',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'knowledge') {
        const query = renderTemplate(data.query, context)
        const output = `围绕「${query || activeExample}」检索到产品反馈、处理策略、常见问题和上下文摘要。`
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
        const prompt = renderTemplate(data.prompt, context)
        const output = `模型 ${data.model ?? '未指定'} 根据提示词生成草稿：${prompt.slice(0, 120)}`
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: 'done',
          input: prompt || '未配置提示词',
          output,
          variable: writeOutput(output),
        })
        return
      }

      if (data.kind === 'tool') {
        const input = JSON.stringify(context, null, 2)
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
        const result = evaluateCondition(data.condition, context)
        branchOpen = result.passed
        steps.push({
          nodeId: node.id,
          title: `${index + 1}. ${data.label}`,
          status: result.passed ? 'routed' : 'skipped',
          input: renderTemplate(data.condition, context) || '未配置判断规则',
          output: result.passed ? `${result.detail} 已继续执行。` : `${result.detail} 后续非输出节点将跳过。`,
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
    setNotice(`已按 ${order.length} 个节点的连线顺序完成运行。`)
  }

  const saveWorkflow = () => {
    const updatedAt = new Date().toISOString()
    const payload = createWorkflowDefinition(nodes, edges, updatedAt)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(payload))
    setLastSavedAt(updatedAt)
    setNotice('已保存到当前浏览器，下次打开会自动恢复。')
  }

  const exportWorkflow = () => {
    const payload = JSON.stringify(createWorkflowDefinition(nodes, edges, new Date().toISOString()), null, 2)
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

        setNodes(parsed.nodes)
        setEdges(parsed.edges)
        setSelectedNodeId(parsed.nodes[0]?.id ?? '')
        setRunSteps([])
        setLastSavedAt(parsed.updatedAt ?? '')
        setNotice('已导入工作流。需要长期保留时请点击保存。')
      } catch {
        setNotice('导入失败：文件不是合法 JSON。')
      } finally {
        event.target.value = ''
      }
    }
    reader.readAsText(file)
  }

  const resetWorkflow = () => {
    setNodes(initialNodes)
    setEdges(initialEdges)
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
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p>AI 工作流编排</p>
            <h1>设计、调试并导出你的模型工作流</h1>
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
            <button type="button" className="primary" onClick={runWorkflow}>
              <Play size={17} />
              运行
            </button>
          </div>
        </header>

        <div className="canvas-wrap">
          {(notice || lastSavedAt) && (
            <div className="workspace-notice">
              <span>{notice || '当前工作流有本地保存记录。'}</span>
              {lastSavedAt && <time>保存时间：{new Date(lastSavedAt).toLocaleString('zh-CN')}</time>}
            </div>
          )}
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, node) => setSelectedNodeId(node.id)}
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

          <label>
            名称
            <input
              value={selectedNode.data.label}
              onChange={(event) => updateSelectedNode({ label: event.target.value })}
            />
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
                  <option>gpt-5.4-mini</option>
                  <option>gpt-5.4</option>
                  <option>gpt-5.3-codex</option>
                </select>
              </label>
              <label>
                提示词
                <textarea
                  rows={6}
                  value={selectedNode.data.prompt}
                  onChange={(event) => updateSelectedNode({ prompt: event.target.value })}
                />
              </label>
            </>
          )}

          {selectedNode.data.kind === 'knowledge' && (
            <label>
              检索语句
              <input
                value={selectedNode.data.query}
                onChange={(event) => updateSelectedNode({ query: event.target.value })}
              />
            </label>
          )}

          {selectedNode.data.kind === 'tool' && (
            <label>
              工具名称
              <input
                value={selectedNode.data.toolName}
                onChange={(event) => updateSelectedNode({ toolName: event.target.value })}
              />
            </label>
          )}

          {selectedNode.data.kind === 'condition' && (
            <label>
              判断规则
              <textarea
                value={selectedNode.data.condition}
                onChange={(event) => updateSelectedNode({ condition: event.target.value })}
              />
            </label>
          )}

          <label>
            输出变量名
            <input
              value={selectedNode.data.outputKey ?? ''}
              onChange={(event) => updateSelectedNode({ outputKey: event.target.value })}
              placeholder="可选"
            />
          </label>
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
                className={clsx(activeExample === example && 'active')}
                key={example}
                onClick={() => setActiveExample(example)}
              >
                {example}
              </button>
            ))}
          </div>

          <div className="run-log">
            {runSteps.length === 0 ? (
              <div className="empty-run">
                <Sparkles size={18} />
                <span>点击运行后，可以查看每个节点的模拟输出。</span>
              </div>
            ) : (
              runSteps.map((step) => (
                <article key={step.nodeId}>
                  <span className={clsx('status-dot', step.status)} />
                  <div>
                    <strong>{step.title}</strong>
                    <dl>
                      <div>
                        <dt>输入</dt>
                        <dd>{step.input}</dd>
                      </div>
                      <div>
                        <dt>输出</dt>
                        <dd>{step.output}</dd>
                      </div>
                      {step.variable && (
                        <div>
                          <dt>写入</dt>
                          <dd>{step.variable}</dd>
                        </div>
                      )}
                    </dl>
                  </div>
                </article>
              ))
            )}
          </div>
        </section>

        <section className="panel json-panel">
          <div className="panel-title">
            <Code2 size={16} />
            <span>定义摘要</span>
          </div>
          <pre>{JSON.stringify({ nodes: nodes.length, edges: edges.length, variables }, null, 2)}</pre>
        </section>
      </aside>
    </main>
  )
}

export default App
