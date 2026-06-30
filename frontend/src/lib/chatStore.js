/*
 * chatStore — persistence for chat threads.
 *
 * Today: the browser's localStorage (key below). Real history that survives
 * reloads, scoped to this browser/device. No backend coupling.
 *
 * ── SWAP SEAM ──────────────────────────────────────────────────────────────
 * To get cross-device history, back these four functions with a server API
 * (e.g. GET/POST/DELETE /threads keyed by the signed-in user) instead of
 * localStorage. The runtime only calls load/save/makeTitle — nothing else
 * needs to change.
 * ───────────────────────────────────────────────────────────────────────────
 */
const KEY = 'glowstar.threads.v1'

export function loadThreads() {
  try {
    const raw = localStorage.getItem(KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function saveThreads(threads) {
  try {
    localStorage.setItem(KEY, JSON.stringify(threads))
  } catch {
    /* quota / private-mode — history just won't persist this session */
  }
}

// Derive a sidebar title from the first user message.
export function makeTitle(text) {
  const t = (text || '').trim().replace(/\s+/g, ' ')
  if (!t) return 'New chat'
  return t.length > 60 ? `${t.slice(0, 60)}…` : t
}
