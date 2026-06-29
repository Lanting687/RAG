import { useState, useRef, useEffect } from 'react'
import { sendChatMessage } from './api'

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

const SUGGESTED_QUESTIONS = [
  "What are EY's specific audit engagement steps for a new client?",
  "What is KPMG's policy on travel and reimbursement for audit staff?",
  "What are PwC's quality control procedures for engagement risk assessment?",
  "What does Deloitte's audit methodology say about testing internal controls?",
  "What are ICAEW's requirements for auditor independence and rotation?",
]

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  async function submitQuestion(question: string) {
    if (!question || loading) return

    setInput('')
    setError(null)
    setMessages(prev => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const data = await sendChatMessage(question)
      setMessages(prev => [
        ...prev,
        { role: 'assistant', content: data.answer, sources: data.sources ?? [] },
      ])
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

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Big 4 Audit RAG Chatbot</h1>
        <p style={styles.subtitle}>Ask questions about your audit knowledge base</p>
      </header>

      <div style={styles.chatContainer}>
        {messages.length === 0 && (
          <div style={styles.suggestions}>
            <p style={styles.empty}>No messages yet. Try one of these, or ask your own question.</p>
            {SUGGESTED_QUESTIONS.map((q, i) => (
              <button
                key={i}
                style={styles.suggestionButton}
                onClick={() => submitQuestion(q)}
                disabled={loading}
              >
                {q}
              </button>
            ))}
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} style={msg.role === 'user' ? styles.userBubble : styles.assistantBubble}>
            <div style={styles.roleLabel}>{msg.role === 'user' ? 'You' : 'Assistant'}</div>
            <p style={styles.messageText}>{msg.content}</p>
            {msg.sources && msg.sources.length > 0 && (
              <details style={styles.sources}>
                <summary style={styles.sourcesSummary}>
                  {msg.sources.length} source{msg.sources.length !== 1 ? 's' : ''}
                </summary>
                {msg.sources.map(src => (
                  <div key={src.id} style={styles.sourceItem}>
                    <strong>{src.title}</strong>
                    <p style={styles.sourceSnippet}>
                      {src.content.length > 200 ? src.content.slice(0, 200) + '…' : src.content}
                    </p>
                  </div>
                ))}
              </details>
            )}
          </div>
        ))}

        {loading && (
          <div style={styles.assistantBubble}>
            <div style={styles.roleLabel}>Assistant</div>
            <p style={styles.thinking}>Thinking…</p>
          </div>
        )}

        {error && <p style={styles.error}>{error}</p>}

        <div ref={bottomRef} />
      </div>

      <form onSubmit={handleSubmit} style={styles.form}>
        <input
          style={styles.input}
          type="text"
          placeholder="Ask about audit procedures, standards, or regulations…"
          value={input}
          onChange={e => setInput(e.target.value)}
          disabled={loading}
        />
        <button style={styles.button} type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    maxWidth: 800,
    margin: '0 auto',
    fontFamily: 'system-ui, sans-serif',
    padding: '0 16px',
    boxSizing: 'border-box',
    backgroundColor: '#d1fae5',
  },
  header: { padding: '24px 0 8px', borderBottom: '1px solid #e5e7eb' },
  title: { margin: 0, fontSize: 22, fontWeight: 700, color: '#111827' },
  subtitle: { margin: '4px 0 0', fontSize: 14, color: '#6b7280' },
  chatContainer: {
    flex: 1,
    overflowY: 'auto',
    padding: '16px 0',
    display: 'flex',
    flexDirection: 'column',
    gap: 12,
  },
  empty: { color: '#9ca3af', textAlign: 'center', marginTop: 40, fontSize: 14 },
  suggestions: { display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 },
  suggestionButton: {
    textAlign: 'left',
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #a7f3d0',
    background: '#ecfdf5',
    color: '#065f46',
    fontSize: 13,
    cursor: 'pointer',
  },
  userBubble: {
    alignSelf: 'flex-end',
    background: '#2563eb',
    color: '#fff',
    borderRadius: '12px 12px 2px 12px',
    padding: '10px 14px',
    maxWidth: '75%',
  },
  assistantBubble: {
    alignSelf: 'flex-start',
    background: '#f3f4f6',
    color: '#111827',
    borderRadius: '12px 12px 12px 2px',
    padding: '10px 14px',
    maxWidth: '85%',
  },
  roleLabel: { fontSize: 11, fontWeight: 600, opacity: 0.7, marginBottom: 4, textTransform: 'uppercase' },
  messageText: { margin: 0, lineHeight: 1.6, whiteSpace: 'pre-wrap' },
  thinking: { margin: 0, fontStyle: 'italic', opacity: 0.6 },
  sources: { marginTop: 8 },
  sourcesSummary: { fontSize: 12, cursor: 'pointer', color: '#4b5563' },
  sourceItem: { marginTop: 6, padding: '6px 8px', background: '#e5e7eb', borderRadius: 6 },
  sourceSnippet: { margin: '2px 0 0', fontSize: 12, color: '#6b7280' },
  error: { color: '#dc2626', fontSize: 14, textAlign: 'center' },
  form: { display: 'flex', gap: 8, padding: '12px 0 20px', borderTop: '1px solid #e5e7eb' },
  input: {
    flex: 1,
    padding: '10px 14px',
    borderRadius: 8,
    border: '1px solid #d1d5db',
    fontSize: 14,
    outline: 'none',
  },
  button: {
    padding: '10px 20px',
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    borderRadius: 8,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  },
}
