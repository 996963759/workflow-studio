import { type ReactNode, useEffect, useMemo, useRef, useState } from 'react'
import {
  Bot,
  Building2,
  ExternalLink,
  Image as ImageIcon,
  LoaderCircle,
  LogOut,
  MessageSquareText,
  Plus,
  Send,
  UserRound,
  Volume2,
} from 'lucide-react'
import { parseMessageBlocks, type MessageBlock } from './messageMedia'
import './CustomerChat.css'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000'
const AUTH_STORAGE_KEY = 'workflow-studio.auth-session'
const ACTIVE_WORKSPACE_STORAGE_KEY = 'workflow-studio.active-workspace-id'
const CUSTOMER_HISTORY_LIMIT = 6
const CUSTOMER_HISTORY_MESSAGE_LIMIT = 1200

type AuthSession = {
  token: string
  user: { id: string; username: string; created_at: string }
}

type Workspace = {
  id: string
  name: string
  role: 'owner' | 'editor' | 'viewer' | 'customer'
}

type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  createdAt: string
  status?: 'completed' | 'needs_clarification' | 'error'
}

type CustomerChatResponse = {
  status: 'completed' | 'needs_clarification' | 'error'
  reply: string
  run_id?: string | null
}

const welcomeMessage = (): ChatMessage => ({
  id: `welcome-${Date.now()}`,
  role: 'assistant',
  content: '您好，请问有什么可以帮您？',
  createdAt: new Date().toISOString(),
})

const loadSession = (): AuthSession | null => {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY)
    return raw ? (JSON.parse(raw) as AuthSession) : null
  } catch {
    return null
  }
}

const messageId = () => `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`

const compactHistoryContent = (value: string) => {
  const content = value.trim()
  if (content.length <= CUSTOMER_HISTORY_MESSAGE_LIMIT) return content
  return `${content.slice(0, CUSTOMER_HISTORY_MESSAGE_LIMIT)}\n...（历史消息已截断）`
}

type MarkdownBlock =
  | { type: 'heading'; level: number; content: string }
  | { type: 'paragraph'; lines: string[] }
  | { type: 'list'; items: string[] }

const INLINE_MARKDOWN_PATTERN = /(\*\*[^*]+\*\*|`[^`]+`)/g

const renderInlineMarkdown = (value: string, keyPrefix: string): ReactNode[] => {
  const nodes: ReactNode[] = []
  let cursor = 0

  Array.from(value.matchAll(INLINE_MARKDOWN_PATTERN)).forEach((match, index) => {
    const start = match.index ?? 0
    if (start > cursor) nodes.push(value.slice(cursor, start))

    const token = match[0]
    if (token.startsWith('**')) {
      nodes.push(<strong key={`${keyPrefix}-strong-${index}`}>{token.slice(2, -2)}</strong>)
    } else {
      nodes.push(<code key={`${keyPrefix}-code-${index}`}>{token.slice(1, -1)}</code>)
    }
    cursor = start + token.length
  })

  if (cursor < value.length) nodes.push(value.slice(cursor))
  return nodes
}

const parseMarkdownBlocks = (content: string): MarkdownBlock[] => {
  const blocks: MarkdownBlock[] = []
  let paragraphLines: string[] = []
  let listItems: string[] = []

  const flushParagraph = () => {
    if (paragraphLines.length > 0) {
      blocks.push({ type: 'paragraph', lines: paragraphLines })
      paragraphLines = []
    }
  }

  const flushList = () => {
    if (listItems.length > 0) {
      blocks.push({ type: 'list', items: listItems })
      listItems = []
    }
  }

  content.replace(/\r\n/g, '\n').split('\n').forEach((rawLine) => {
    const line = rawLine.trim()
    if (!line) {
      flushParagraph()
      flushList()
      return
    }

    const heading = line.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      flushParagraph()
      flushList()
      blocks.push({ type: 'heading', level: heading[1].length, content: heading[2].trim() })
      return
    }

    const listItem = line.match(/^[-*]\s+(.+)$/) ?? line.match(/^\d+[.)]\s+(.+)$/)
    if (listItem) {
      flushParagraph()
      listItems.push(listItem[1].trim())
      return
    }

    flushList()
    paragraphLines.push(line)
  })

  flushParagraph()
  flushList()
  return blocks
}

function MarkdownText({ content }: { content: string }) {
  const blocks = parseMarkdownBlocks(content)

  return (
    <div className="customer-message-markdown">
      {blocks.map((block, index) => {
        if (block.type === 'heading') {
          const HeadingTag = block.level <= 3 ? 'h3' : 'h4'
          return (
            <HeadingTag key={`heading-${index}`}>
              {renderInlineMarkdown(block.content, `heading-${index}`)}
            </HeadingTag>
          )
        }

        if (block.type === 'list') {
          return (
            <ul key={`list-${index}`}>
              {block.items.map((item, itemIndex) => (
                <li key={`item-${index}-${itemIndex}`}>
                  {renderInlineMarkdown(item, `item-${index}-${itemIndex}`)}
                </li>
              ))}
            </ul>
          )
        }

        return (
          <p key={`paragraph-${index}`}>
            {block.lines.map((line, lineIndex) => (
              <span key={`line-${index}-${lineIndex}`}>
                {lineIndex > 0 && <br />}
                {renderInlineMarkdown(line, `line-${index}-${lineIndex}`)}
              </span>
            ))}
          </p>
        )
      })}
    </div>
  )
}

function MessageMedia({ block }: { block: Extract<MessageBlock, { type: 'audio' | 'image' }> }) {
  const [failed, setFailed] = useState(false)

  return (
    <section className={`customer-message-media ${block.type}`}>
      <header>
        <span>{block.type === 'audio' ? <Volume2 size={15} /> : <ImageIcon size={15} />}</span>
        <strong>{block.label}</strong>
        <a href={block.url} target="_blank" rel="noreferrer" title="打开原文件" aria-label={`打开${block.label}`}>
          <ExternalLink size={14} />
        </a>
      </header>
      {failed ? (
        <p className="customer-media-error">资源加载失败或链接已过期，请打开原文件查看。</p>
      ) : block.type === 'audio' ? (
        <audio controls preload="metadata" src={block.url} onError={() => setFailed(true)}>
          当前浏览器不支持音频播放。
        </audio>
      ) : (
        <img src={block.url} alt={block.label} loading="lazy" onError={() => setFailed(true)} />
      )}
    </section>
  )
}

function MessageContent({ message }: { message: ChatMessage }) {
  if (message.role === 'user') return <p>{message.content}</p>

  const blocks = parseMessageBlocks(message.content)
  return (
    <div className="customer-message-content">
      {blocks.map((block, index) => (
        block.type === 'text'
          ? <MarkdownText key={`text-${index}`} content={block.content} />
          : <MessageMedia key={`${block.type}-${index}-${block.url}`} block={block} />
      ))}
    </div>
  )
}

export function CustomerChat() {
  const [session, setSession] = useState<AuthSession | null>(() => loadSession())
  const [authMode, setAuthMode] = useState<'login' | 'register'>('login')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [invitationCode, setInvitationCode] = useState('')
  const [authError, setAuthError] = useState('')
  const [workspaces, setWorkspaces] = useState<Workspace[]>([])
  const [workspaceId, setWorkspaceId] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>(() => [welcomeMessage()])
  const [draft, setDraft] = useState('')
  const [sending, setSending] = useState(false)
  const [workspaceLoading, setWorkspaceLoading] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement | null>(null)

  const activeWorkspace = useMemo(
    () => workspaces.find((workspace) => workspace.id === workspaceId),
    [workspaceId, workspaces],
  )

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, sending])

  useEffect(() => {
    if (!session) return
    let canceled = false
    const loadWorkspaces = async () => {
      setWorkspaceLoading(true)
      try {
        const response = await fetch(`${API_BASE_URL}/api/workspaces`, {
          headers: { Authorization: `Bearer ${session.token}` },
        })
        if (response.status === 401) {
          window.localStorage.removeItem(AUTH_STORAGE_KEY)
          if (!canceled) setSession(null)
          return
        }
        if (!response.ok) throw new Error('load failed')
        const records = (await response.json()) as Workspace[]
        const storedId = window.localStorage.getItem(ACTIVE_WORKSPACE_STORAGE_KEY)
        const customerWorkspace = records.find((workspace) => workspace.role === 'customer')
        const storedWorkspace = records.find((workspace) => workspace.id === storedId)
        const storedCustomerWorkspace = records.find(
          (workspace) => workspace.id === storedId && workspace.role === 'customer',
        )
        const nextId = storedCustomerWorkspace?.id ?? customerWorkspace?.id ?? storedWorkspace?.id ?? records[0]?.id ?? ''
        if (!canceled) {
          setWorkspaces(records)
          setWorkspaceId(nextId)
          if (nextId) window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, nextId)
        }
      } catch {
        if (!canceled) setAuthError('服务暂时不可用，请稍后重试。')
      } finally {
        if (!canceled) setWorkspaceLoading(false)
      }
    }
    void loadWorkspaces()
    return () => {
      canceled = true
    }
  }, [session])

  const authenticate = async () => {
    if (!username.trim() || password.length < 6 || (authMode === 'register' && !invitationCode.trim())) return
    setAuthError('')
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/${authMode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      })
      if (!response.ok) throw new Error('auth failed')
      const nextSession = (await response.json()) as AuthSession
      if (invitationCode.trim()) {
        const invitationResponse = await fetch(`${API_BASE_URL}/api/workspaces/invitations/accept`, {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${nextSession.token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ code: invitationCode.trim() }),
        })
        if (!invitationResponse.ok) throw new Error('invitation failed')
      }
      window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(nextSession))
      setSession(nextSession)
      setPassword('')
      setInvitationCode('')
    } catch (error) {
      setAuthError(
        error instanceof Error && error.message === 'invitation failed'
          ? '邀请码无效、已过期或已被使用。'
          : authMode === 'login'
            ? '账号或密码不正确。'
            : '注册失败，账号可能已存在。',
      )
    }
  }

  const logout = async () => {
    if (session) {
      try {
        await fetch(`${API_BASE_URL}/api/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${session.token}` },
        })
      } catch {
        // The local session is cleared even if the service is temporarily unavailable.
      }
    }
    window.localStorage.removeItem(AUTH_STORAGE_KEY)
    setSession(null)
    setWorkspaces([])
    setWorkspaceId('')
    setMessages([welcomeMessage()])
  }

  const startNewChat = () => {
    setMessages([welcomeMessage()])
    setDraft('')
  }

  const sendMessage = async () => {
    const content = draft.trim()
    if (!content || !session || !workspaceId || sending) return

    const history = messages
      .filter((message) => !message.id.startsWith('welcome-'))
      .slice(-CUSTOMER_HISTORY_LIMIT)
      .map((message) => ({ role: message.role, content: compactHistoryContent(message.content) }))
    const userMessage: ChatMessage = {
      id: messageId(),
      role: 'user',
      content,
      createdAt: new Date().toISOString(),
    }
    setMessages((current) => [...current, userMessage])
    setDraft('')
    setSending(true)

    try {
      const response = await fetch(`${API_BASE_URL}/api/customer-chat/messages`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${session.token}`,
          'Content-Type': 'application/json',
          'X-Workspace-Id': workspaceId,
        },
        body: JSON.stringify({ message: content, history }),
      })
      if (response.status === 401) {
        window.localStorage.removeItem(AUTH_STORAGE_KEY)
        setSession(null)
        return
      }
      if (!response.ok) throw new Error('chat failed')
      const result = (await response.json()) as CustomerChatResponse
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: 'assistant',
          content: result.reply,
          createdAt: new Date().toISOString(),
          status: result.status,
        },
      ])
    } catch {
      setMessages((current) => [
        ...current,
        {
          id: messageId(),
          role: 'assistant',
          content: '消息发送失败，请稍后重试。',
          createdAt: new Date().toISOString(),
          status: 'error',
        },
      ])
    } finally {
      setSending(false)
    }
  }

  if (!session) {
    return (
      <main className="customer-login-shell">
        <section className="customer-login-panel">
          <div className="customer-login-brand">
            <span><Bot size={24} /></span>
            <div>
              <strong>织流智能服务</strong>
              <small>客户服务入口</small>
            </div>
          </div>
          <div className="customer-auth-tabs">
            <button type="button" className={authMode === 'login' ? 'active' : ''} onClick={() => setAuthMode('login')}>
              登录
            </button>
            <button type="button" className={authMode === 'register' ? 'active' : ''} onClick={() => setAuthMode('register')}>
              注册
            </button>
          </div>
          <label>
            账号
            <input value={username} onChange={(event) => setUsername(event.target.value)} autoComplete="username" />
          </label>
          <label>
            密码
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              onKeyDown={(event) => {
                if (event.key === 'Enter') void authenticate()
              }}
            />
          </label>
          <label>
            客户邀请码{authMode === 'login' ? '（首次加入时填写）' : ''}
            <input
              value={invitationCode}
              onChange={(event) => setInvitationCode(event.target.value)}
              autoComplete="off"
            />
          </label>
          {authError && <p>{authError}</p>}
          <button
            type="button"
            onClick={() => void authenticate()}
            disabled={!username.trim() || password.length < 6 || (authMode === 'register' && !invitationCode.trim())}
          >
            {authMode === 'login' ? '登录' : '注册并进入'}
          </button>
        </section>
      </main>
    )
  }

  return (
    <main className="customer-chat-shell">
      <aside className="customer-chat-sidebar">
        <div className="customer-chat-brand">
          <span><Bot size={20} /></span>
          <strong>织流智能服务</strong>
        </div>
        <button type="button" className="customer-new-chat" onClick={startNewChat}>
          <Plus size={16} />
          新对话
        </button>
        <button
          type="button"
          className="customer-mobile-logout"
          onClick={() => void logout()}
          title="退出登录"
          aria-label="退出登录"
        >
          <LogOut size={16} />
        </button>
        <div className="customer-conversation active">
          <MessageSquareText size={15} />
          <span>当前对话</span>
        </div>
        <div className="customer-account">
          <label>
            <Building2 size={14} />
            <select
              aria-label="服务空间"
              value={workspaceId}
              disabled={workspaceLoading || workspaces.length <= 1}
              onChange={(event) => {
                setWorkspaceId(event.target.value)
                window.localStorage.setItem(ACTIVE_WORKSPACE_STORAGE_KEY, event.target.value)
                startNewChat()
              }}
            >
              {workspaces.map((workspace) => <option key={workspace.id} value={workspace.id}>{workspace.name}</option>)}
            </select>
          </label>
          <div>
            <UserRound size={15} />
            <span>{session.user.username}</span>
            <button type="button" onClick={() => void logout()} title="退出登录" aria-label="退出登录">
              <LogOut size={15} />
            </button>
          </div>
        </div>
      </aside>

      <section className="customer-chat-main">
        <header className="customer-chat-header">
          <div>
            <strong>{activeWorkspace?.name ?? '智能服务'}</strong>
            <span><i /> 在线</span>
          </div>
        </header>

        <div className="customer-message-list" aria-live="polite">
          <div className="customer-message-column">
            {messages.map((message) => (
              <article key={message.id} className={`customer-message ${message.role}`}>
                <span className="customer-message-avatar">
                  {message.role === 'assistant' ? <Bot size={17} /> : <UserRound size={17} />}
                </span>
                <div>
                  <MessageContent message={message} />
                  <time>{new Date(message.createdAt).toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}</time>
                </div>
              </article>
            ))}
            {sending && (
              <article className="customer-message assistant pending">
                <span className="customer-message-avatar"><Bot size={17} /></span>
                <div><LoaderCircle size={18} className="customer-spinner" /></div>
              </article>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>

        <footer className="customer-composer-wrap">
          <div className="customer-composer">
            <textarea
              aria-label="输入消息"
              placeholder="请输入您的问题"
              rows={1}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault()
                  void sendMessage()
                }
              }}
            />
            <button
              type="button"
              aria-label="发送消息"
              title="发送消息"
              disabled={!draft.trim() || sending || !workspaceId}
              onClick={() => void sendMessage()}
            >
              <Send size={18} />
            </button>
          </div>
        </footer>
      </section>
    </main>
  )
}
