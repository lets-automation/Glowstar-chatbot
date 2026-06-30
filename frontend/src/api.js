// api.js - all calls to the Python backend.
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Ask a question with LIVE status updates (streaming).
// callbacks: onStatus(msg), onResult(data), onError(msg)
export async function streamQuestion(question, sessionId, { onStatus, onResult, onError }) {
  let res
  try {
    res = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, session_id: sessionId }),
    })
  } catch {
    onError('Cannot reach the server.')
    return
  }
  if (!res.ok || !res.body) {
    onError(`Request failed (${res.status}).`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buffer.indexOf('\n\n')) >= 0) {
      const raw = buffer.slice(0, idx).replace(/^data: /, '').trim()
      buffer = buffer.slice(idx + 2)
      if (!raw) continue
      let evt
      try { evt = JSON.parse(raw) } catch { continue }
      if (evt.type === 'status') onStatus(evt.message)
      else if (evt.type === 'result') onResult(evt.data)
      else if (evt.type === 'error') onError(evt.message)
    }
  }
}

// Send thumbs up/down feedback on an answer.
export async function sendFeedback(question, answer, helpful, sessionId) {
  try {
    await fetch(`${API_URL}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, answer, helpful, session_id: sessionId }),
    })
  } catch { /* feedback is best-effort */ }
}

// Export a query's results as a file (excel | pdf) and trigger a download.
export async function exportData(query, format) {
  const res = await fetch(`${API_URL}/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, format }),
  })
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'pdf' ? 'report.pdf' : 'report.xlsx'
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export async function checkHealth() {
  try {
    const res = await fetch(`${API_URL}/health`)
    return res.ok
  } catch {
    return false
  }
}
