import { useState, useRef, useEffect } from 'react'
import { sendChatMessage } from './api'
import './App.css'

interface Source {
  id: number
  title: string
  content: string
  metadata?: Record<string, unknown>
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
}

interface Chat {
  id: string
  title: string
  messages: Message[]
}

const PROMPT_CARDS = [
  { title: 'Engagement Planning', icon: '📋', prompt: "What are EY's specific audit engagement steps for a new client?" },
  { title: 'Internal Controls',   icon: '🔒', prompt: "What does audit methodology say about testing internal controls?" },
  { title: 'Independence',        icon: '⚖️', prompt: "What are ICAEW's requirements for auditor independence and rotation?" },
  { title: 'Risk Assessment',     icon: '📊', prompt: "What are PwC's quality control procedures for engagement risk assessment?" },
]

const CAPABILITY_CHIPS = ['Confluence Search', 'Source References', 'Semantic Retrieval', 'Audit Guidance']

type ActiveNav = 'home' | 'history'

export default function App() {
  const [chats, setChats] = useState<Chat[]>([])
  const [currentChatId, setCurrentChatId] = useState<string | null>(null)
  const [activeNav, setActiveNav] = useState<ActiveNav>('home')
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [darkMode, setDarkMode] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const currentMessages = chats.find(c => c.id === currentChatId)?.messages ?? []

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [currentMessages, loading])

  async function submitQuestion(question: string) {
    if (!question || loading) return
    setInput('')
    setError(null)
    setSidebarOpen(false)
    setActiveNav('home')

    let chatId = currentChatId
    if (!chatId) {
      chatId = crypto.randomUUID()
      const title = question.length > 42 ? question.slice(0, 42) + '…' : question
      setChats(prev => [{ id: chatId!, title, messages: [] }, ...prev])
      setCurrentChatId(chatId)
    }

    const userMsg: Message = { role: 'user', content: question }
    setChats(prev => prev.map(c => c.id === chatId ? { ...c, messages: [...c.messages, userMsg] } : c))
    setLoading(true)

    try {
      const data = await sendChatMessage(question)
      const assistantMsg: Message = { role: 'assistant', content: data.answer, sources: data.sources ?? [] }
      setChats(prev => prev.map(c => c.id === chatId ? { ...c, messages: [...c.messages, assistantMsg] } : c))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unexpected error')
    } finally {
      setLoading(false)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    await submitQuestion(input.trim())
  }

  function handleHome() {
    setCurrentChatId(null)
    setInput('')
    setError(null)
    setActiveNav('home')
    setSidebarOpen(false)
  }

  function handleNewChat() {
    setCurrentChatId(null)
    setInput('')
    setError(null)
    setActiveNav('home')
    setSidebarOpen(false)
  }

  function handleSelectChat(id: string) {
    setCurrentChatId(id)
    setInput('')
    setError(null)
    setActiveNav('home')
    setSidebarOpen(false)
  }

  return (
    <div className={`app${darkMode ? ' dark' : ''}`}>

      {/* Mobile overlay */}
      {sidebarOpen && <div className="mobile-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* ── Sidebar ── */}
      <aside className={`sidebar${sidebarOpen ? ' open' : ''}`}>

        <div className="sidebar-logo">
          <div className="logo-icon">A</div>
          <span className="logo-text">Audit Knowledge<br />Assistant</span>
        </div>

        <nav className="sidebar-nav">
          <button
            className={`nav-item${activeNav === 'home' ? ' active' : ''}`}
            onClick={handleHome}
          >
            <span className="nav-icon">🏠</span> Home
          </button>
          <button className="nav-item" onClick={handleNewChat}>
            <span className="nav-icon">✏️</span> New Chat
          </button>
          <button
            className={`nav-item${activeNav === 'history' ? ' active' : ''}`}
            onClick={() => setActiveNav(n => n === 'history' ? 'home' : 'history')}
          >
            <span className="nav-icon">🕐</span> Chat History
          </button>
        </nav>

        {/* Chat history list */}
        <div className="history-section">
          <p className="history-header">Recent</p>
          <div className="history-list">
            {chats.length === 0
              ? <p className="history-empty">No conversations yet</p>
              : chats.map(chat => (
                  <button
                    key={chat.id}
                    className={`history-item${chat.id === currentChatId ? ' active' : ''}`}
                    onClick={() => handleSelectChat(chat.id)}
                    title={chat.title}
                  >
                    💬 {chat.title}
                  </button>
                ))
            }
          </div>
        </div>

        <div className="sidebar-bottom">
          <button className="theme-toggle" onClick={() => setDarkMode(d => !d)}>
            {darkMode ? '☀️ Light mode' : '🌙 Dark mode'}
          </button>
          <p className="version">v1.0.0</p>
        </div>

      </aside>

      {/* ── Main panel ── */}
      <main className="main">

        {/* Mobile top bar */}
        <div className="mobile-bar">
          <button className="hamburger" onClick={() => setSidebarOpen(o => !o)}>☰</button>
          <span className="mobile-title">Audit Knowledge Assistant</span>
          <button className="hamburger" onClick={() => setDarkMode(d => !d)}>
            {darkMode ? '☀️' : '🌙'}
          </button>
        </div>

        {/* Chat / welcome area */}
        <div className="chat-area">
          {currentMessages.length === 0 ? (
            <div className="empty-state">
              <div className="product-icon">📚</div>
              <h1 className="empty-title">Audit Knowledge Assistant</h1>
              <p className="empty-subtitle">
                Retrieve relevant audit guidance and receive source-backed answers.
              </p>

              <div className="chips">
                {CAPABILITY_CHIPS.map(chip => (
                  <span key={chip} className="chip">{chip}</span>
                ))}
              </div>

              <div className="card-grid">
                {PROMPT_CARDS.map(card => (
                  <button
                    key={card.title}
                    className="prompt-card"
                    disabled={loading}
                    onClick={() => submitQuestion(card.prompt)}
                  >
                    <span className="card-icon">{card.icon}</span>
                    <span className="card-title">{card.title}</span>
                    <span className="card-desc">{card.prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="messages">
              {currentMessages.map((msg, i) => (
                <div key={i} className={msg.role === 'user' ? 'user-bubble' : 'assistant-bubble'}>
                  <div className="role-label">{msg.role === 'user' ? 'You' : 'Assistant'}</div>
                  <p className="message-text">{msg.content}</p>
                  {msg.sources && msg.sources.length > 0 && (
                    <details>
                      <summary className="sources-summary">
                        {msg.sources.length} source{msg.sources.length !== 1 ? 's' : ''}
                      </summary>
                      {msg.sources.map(src => (
                        <div key={src.id} className="source-item">
                          <div className="source-title">{src.title}</div>
                          <p className="source-snippet">
                            {src.content.length > 200 ? src.content.slice(0, 200) + '…' : src.content}
                          </p>
                        </div>
                      ))}
                    </details>
                  )}
                </div>
              ))}

              {loading && (
                <div className="assistant-bubble">
                  <div className="role-label">Assistant</div>
                  <p className="thinking">Thinking…</p>
                </div>
              )}

              {error && <p className="error-msg">{error}</p>}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {/* ── Input bar ── */}
        <div className="input-bar">
          <form className="input-form" onSubmit={handleSubmit}>
            <input
              className="input-field"
              type="text"
              placeholder="Ask about audit methodology, standards or procedures..."
              value={input}
              onChange={e => setInput(e.target.value)}
              disabled={loading}
            />
            <button
              className="send-button"
              type="submit"
              disabled={loading || !input.trim()}
            >
              Send
            </button>
          </form>
        </div>

      </main>
    </div>
  )
}
