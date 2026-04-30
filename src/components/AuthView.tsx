import { Shield } from 'lucide-react'
import clsx from 'clsx'

type AuthViewProps = {
  authMode: 'login' | 'register'
  authNotice: string
  authPassword: string
  authUsername: string
  onPasswordChange: (value: string) => void
  onSubmit: () => void
  onUsernameChange: (value: string) => void
  setAuthMode: (mode: 'login' | 'register') => void
}

export function AuthView({
  authMode,
  authNotice,
  authPassword,
  authUsername,
  onPasswordChange,
  onSubmit,
  onUsernameChange,
  setAuthMode,
}: AuthViewProps) {
  return (
    <main className="auth-shell">
      <section className="auth-panel">
        <div className="brand auth-brand">
          <span>
            <Shield size={22} />
          </span>
          <div>
            <strong>流程工坊</strong>
            <small>登录后进入工作台</small>
          </div>
        </div>
        <div className="auth-tabs">
          <button type="button" className={clsx(authMode === 'login' && 'active')} onClick={() => setAuthMode('login')}>
            登录
          </button>
          <button
            type="button"
            className={clsx(authMode === 'register' && 'active')}
            onClick={() => setAuthMode('register')}
          >
            注册
          </button>
        </div>
        <label>
          账号
          <input value={authUsername} onChange={(event) => onUsernameChange(event.target.value)} placeholder="至少 3 个字符" />
        </label>
        <label>
          密码
          <input
            type="password"
            value={authPassword}
            onChange={(event) => onPasswordChange(event.target.value)}
            placeholder="至少 6 个字符"
            onKeyDown={(event) => {
              if (event.key === 'Enter') onSubmit()
            }}
          />
        </label>
        {authNotice && <p className="auth-notice">{authNotice}</p>}
        <button type="button" className="primary" onClick={onSubmit}>
          {authMode === 'login' ? '登录' : '注册并登录'}
        </button>
      </section>
    </main>
  )
}
