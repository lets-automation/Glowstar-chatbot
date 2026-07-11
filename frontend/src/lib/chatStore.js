/*
 * chatStore — localStorage persistence for chat threads.
 *
 * Since the server-side history store (backend /threads + the history-db
 * Postgres container) this is the FALLBACK, not the primary: the runtime
 * uses the API for cross-device history and only falls back here when the
 * server is unreachable or history storage is disabled (HISTORY_DB_URL empty).
 *
 * It is also the MIGRATION SOURCE: on the first load after the switch, any
 * threads found here are pushed up to the server once (guarded by the
 * migrated flag below, so wiping server history can't resurrect them).
 */
const KEY = 'glowstar.threads.v1'
const MIGRATED_KEY = 'glowstar.threads.migrated.v1'

// Has this browser already pushed its localStorage history to the server?
export function isMigrated() {
  try {
    return localStorage.getItem(MIGRATED_KEY) === '1'
  } catch {
    return true // storage unusable -> nothing to migrate anyway
  }
}

export function markMigrated() {
  try {
    localStorage.setItem(MIGRATED_KEY, '1')
  } catch {
    /* private mode / storage disabled */
  }
}

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
    return
  } catch {
    /* likely quota: big export snapshots can exceed localStorage's ~5MB */
  }
  // Fallback 1: keep history but trim bulky export rows to a small preview.
  try {
    const slim = threads.map((t) => ({
      ...t,
      messages: (t.messages || []).map((m) =>
        m.exportRows?.length > 50
          ? { ...m, exportRows: m.exportRows.slice(0, 50), exportTruncated: true }
          : m,
      ),
    }))
    localStorage.setItem(KEY, JSON.stringify(slim))
    return
  } catch {
    /* still too big */
  }
  // Fallback 2: keep only the 10 most recent threads, titles intact. The bulky
  // export rows/widgets are dropped, but exportQuery (small text) survives and
  // exportTruncated is set — so the UI can still offer a full-data re-run
  // export instead of silently losing the download.
  try {
    const minimal = threads.slice(0, 10).map((t) => ({
      ...t,
      messages: (t.messages || []).map(({ exportRows, exportColumns, widgets, ...m }) =>
        exportRows?.length ? { ...m, exportTruncated: true } : m,
      ),
    }))
    localStorage.setItem(KEY, JSON.stringify(minimal))
  } catch {
    /* private mode / storage disabled — history won't persist this session */
  }
}

/*
 * UNSYNCED backup (server mode only).
 * A durable local copy of threads whose latest server save is NOT confirmed —
 * because the PUT failed, or the tab closed within the save debounce. Written
 * only at those at-risk moments (not on every change), and drained on the next
 * successful save / mount reconciliation. This is the safety net that stops a
 * dropped save from silently losing a conversation in server mode.
 */
const UNSYNCED_KEY = 'glowstar.unsynced.v1'

export function loadUnsynced() {
  try {
    const raw = localStorage.getItem(UNSYNCED_KEY)
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// Merge threads into the backup (by id; newest updatedAt wins). Best-effort.
export function stashUnsynced(threads) {
  try {
    const byId = new Map(loadUnsynced().map((t) => [t.id, t]))
    for (const t of threads || []) {
      if (!t?.id) continue
      const have = byId.get(t.id)
      if (!have || (t.updatedAt || 0) >= (have.updatedAt || 0)) byId.set(t.id, t)
    }
    localStorage.setItem(UNSYNCED_KEY, JSON.stringify(Array.from(byId.values())))
  } catch {
    /* quota/private-mode: the backup is best-effort */
  }
}

// Drop the given ids from the backup once they're confirmed saved server-side.
export function clearUnsynced(ids) {
  if (!ids?.length) return
  try {
    const drop = new Set(ids)
    const keep = loadUnsynced().filter((t) => !drop.has(t.id))
    if (keep.length) localStorage.setItem(UNSYNCED_KEY, JSON.stringify(keep))
    else localStorage.removeItem(UNSYNCED_KEY)
  } catch {
    /* ignore */
  }
}

// Derive a sidebar title from the first user message.
export function makeTitle(text) {
  const t = (text || '').trim().replace(/\s+/g, ' ')
  if (!t) return 'New chat'
  return t.length > 60 ? `${t.slice(0, 60)}…` : t
}
