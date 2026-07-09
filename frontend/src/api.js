// api.js - all calls to the Python backend.
import { loadAuth, clearAuth } from './lib/authStore'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// Fired when any call gets a 401 (missing/expired/invalid token), so the app
// can drop back to the login screen. Set once from App.jsx at startup.
let onUnauthorized = null
export function setUnauthorizedHandler(fn) {
  onUnauthorized = fn
}

function authHeaders(extra = {}) {
  const auth = loadAuth()
  return auth ? { ...extra, Authorization: `Bearer ${auth.token}` } : extra
}

function handle401(status) {
  if (status === 401) {
    clearAuth()
    onUnauthorized?.()
  }
}

// Log in with username + password. Returns the auth record on success, throws
// with a user-facing message on failure (wrong credentials, server down).
export async function login(username, password) {
  let res
  try {
    res = await fetch(`${API_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    })
  } catch {
    throw new Error('Cannot reach the server.')
  }
  if (!res.ok) {
    if (res.status === 401) throw new Error('Incorrect username or password.')
    throw new Error(`Login failed (${res.status}).`)
  }
  return res.json() // { access_token, display_name, expires_in_minutes }
}

// Ask a question with LIVE status updates (streaming).
// callbacks: onStatus(msg), onResult(data), onError(msg)
// attachments: [{ file_id, filename }] already uploaded via uploadFile().
export async function streamQuestion(question, sessionId, { onStatus, onResult, onError, signal, attachments = [] }) {
  let res
  try {
    res = await fetch(`${API_URL}/chat/stream`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ question, session_id: sessionId, attachments }),
      signal,
    })
  } catch (e) {
    if (e?.name === 'AbortError') return
    onError('Cannot reach the server.')
    return
  }
  handle401(res.status)
  if (!res.ok || !res.body) {
    onError(res.status === 401 ? 'Your session expired — please log in again.' : `Request failed (${res.status}).`)
    return
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  try {
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
  } catch (e) {
    if (e?.name !== 'AbortError') onError('Connection interrupted.')
  }
}

// Send thumbs up/down feedback on an answer.
export async function sendFeedback(question, answer, helpful, sessionId) {
  try {
    const res = await fetch(`${API_URL}/feedback`, {
      method: 'POST',
      headers: authHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ question, answer, helpful, session_id: sessionId }),
    })
    handle401(res.status)
  } catch { /* feedback is best-effort */ }
}

// Export a query's results as a file (excel | pdf) and trigger a download.
export async function exportData(query, format) {
  const res = await fetch(`${API_URL}/export`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ query, format }),
  })
  handle401(res.status)
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

// Upload an image or file to the backend. Returns { file_id, filename, ... }.
// Used by the composer's image/file pickers; see /upload in app/api/main.py.
export async function uploadFile(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_URL}/upload`, { method: 'POST', headers: authHeaders(), body: form })
  handle401(res.status)
  if (!res.ok) throw new Error(`Upload failed (${res.status}).`)
  return res.json()
}

// Export the EXACT rows the chat already showed as Excel/PDF — a stable
// snapshot (no query re-run), so the file is identical every download.
export async function exportRows(columns, rows, format, title = 'Report') {
  const res = await fetch(`${API_URL}/export_rows`, {
    method: 'POST',
    headers: authHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ columns, rows, format, title }),
  })
  handle401(res.status)
  if (!res.ok) throw new Error('Export failed')
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = format === 'pdf' ? 'report.pdf' : format === 'chart' ? 'chart.png' : 'report.xlsx'
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
