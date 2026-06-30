import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { streamQuestion, exportData, checkHealth } from './api'
import { Widget } from './SandboxedWidget'

// Markdown overrides: open external links safely; let wide tables scroll.
const MD_COMPONENTS = {
  a: ({ node, ...props }) => (
    <a target="_blank" rel="noopener noreferrer" {...props} />
  ),
  table: ({ node, ...props }) => (
    <div className="table-wrap"><table {...props} /></div>
  ),
}

const STARTERS = [
  'How many packets are on jangad?',
  'Total final-packet value',
  'How many employees are from Surat?',
  'Total attendance punches this month',
]

// Session memory: one id per browser session (sessionStorage clears when the
// app/tab is closed -> fresh memory next time; persists across reloads).
function getSessionId() {
  let id = sessionStorage.getItem('aastha_session')
  if (!id) {
    id = crypto?.randomUUID?.() || 'sess-' + Date.now() + '-' + Math.floor(Math.random() * 1e6)
    sessionStorage.setItem('aastha_session', id)
  }
  return id
}

export default function App() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [status, setStatus] = useState('')
  const [online, setOnline] = useState(null)
  const sessionId = useRef(getSessionId()).current
  const endRef = useRef(null)

  useEffect(() => { checkHealth().then(setOnline) }, [])
  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, status])

  async function send(text) {
    const question = (text ?? input).trim()
    if (!question || loading) return
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: question }])
    setLoading(true)
    setStatus('Starting…')

    await streamQuestion(question, sessionId, {
      onStatus: (msg) => setStatus(msg),
      onResult: (data) => {
        setMessages((m) => [...m, {
          role: 'assistant',
          userQuestion: question,
          content: data.answer,
          suggestions: data.suggestions || [],
          citation: data.citation || '',
          exportQuery: data.export_query || null,
          widgets: data.widgets || [],
          feedback: null,
        }])
        setLoading(false); setStatus('')
      },
      onError: (msg) => {
        setMessages((m) => [...m, { role: 'assistant', error: msg }])
        setLoading(false); setStatus('')
      },
    })
  }

  function onSubmit(e) { e.preventDefault(); send() }

  async function handleExport(query, format) {
    try { await exportData(query, format) } catch { alert('Export failed') }
  }

  return (
    <div className="app">
      <header className="header">
        <div className="header-title">
          <span className="logo" aria-hidden="true">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="currentColor">
              <path d="M12 2.6c.5 3.9 1.5 4.9 5.4 5.4-3.9.5-4.9 1.5-5.4 5.4-.5-3.9-1.5-4.9-5.4-5.4 3.9-.5 4.9-1.5 5.4-5.4z" />
              <path d="M18.4 13.2c.3 2 .8 2.5 2.8 2.8-2 .3-2.5.8-2.8 2.8-.3-2-.8-2.5-2.8-2.8 2-.3 2.5-.8 2.8-2.8z" opacity="0.7" />
            </svg>
          </span>
          <h1>GlowStar</h1>
          <span className={`status ${online ? 'up' : 'down'}`}>
            {online === null ? 'connecting' : online ? 'online' : 'offline'}
          </span>
        </div>
        <p>Your GlowStar assistant for packets, labour, jangad, attendance and more — just ask.</p>
      </header>

      <main className="chat">
        {messages.length === 0 && (
          <div className="empty">
            <p>Hello 👋 &nbsp;Here are a few things you can ask me:</p>
            <div className="suggestions">
              {STARTERS.map((s) => (
                <button key={s} className="chip" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`msg ${m.role}`}>
            <div className={`bubble ${m.widgets?.length ? 'wide' : ''}`}>
              {m.error ? (
                <span className="error">⚠️ {m.error}</span>
              ) : (
                <>
                  {m.content && (
                    m.role === 'assistant' ? (
                      <div className="content markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                          {m.content}
                        </ReactMarkdown>
                      </div>
                    ) : (
                      <div className="content">{m.content}</div>
                    )
                  )}

                  {m.widgets?.map((w, wi) => (
                    <Widget
                      key={wi}
                      code={w.code}
                      title={w.title}
                      onPrompt={(text) => send(text)}
                    />
                  ))}

                  {m.citation && <div className="citation">{m.citation}</div>}

                  {m.role === 'assistant' && m.exportQuery && (
                    <div className="actions">
                      <button className="exp" onClick={() => handleExport(m.exportQuery, 'excel')}>⬇ Excel</button>
                      <button className="exp" onClick={() => handleExport(m.exportQuery, 'pdf')}>⬇ PDF</button>
                    </div>
                  )}

                  {m.suggestions?.length > 0 && (
                    <div className="followups">
                      {m.suggestions.map((s) => (
                        <button key={s} className="chip small" onClick={() => send(s)}>{s}</button>
                      ))}
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="msg assistant">
            <div className="bubble">
              <span className="typing"><span className="spinner" /> {status || 'Working…'}</span>
            </div>
          </div>
        )}
        <div ref={endRef} />
      </main>

      <form className="composer" onSubmit={onSubmit}>
        <input value={input} onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question…" disabled={loading} />
        <button type="submit" disabled={loading || !input.trim()}>Send</button>
      </form>
    </div>
  )
}
