import { useCallback, useEffect, useRef, useState } from 'react'
import {
  apiDeleteThread,
  apiGetThread,
  apiListThreads,
  apiSaveThread,
  streamQuestion,
  uploadFile,
} from '../api'
import {
  loadThreads,
  saveThreads,
  makeTitle,
  isMigrated,
  markMigrated,
  loadUnsynced,
  stashUnsynced,
  clearUnsynced,
} from '../lib/chatStore'

// Client-minted thread id. Uses crypto.randomUUID when available so two devices
// starting a chat in the same millisecond can't collide onto one id (which, in
// the shared server pool, would merge two different conversations into one row).
function newThreadId() {
  const rand =
    (typeof crypto !== 'undefined' && crypto.randomUUID && crypto.randomUUID()) ||
    `${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`
  return `t-${Date.now()}-${rand}`
}

// Defensive: never surface raw SQL in a chat reply, even if the model embeds a
// fenced ```sql block. The query is intentionally hidden from responses.
function stripSql(text) {
  return (text || '').replace(/```sql[\s\S]*?```/gi, '').replace(/\n{3,}/g, '\n\n').trim()
}

// Bound what one message contributes to a server save: export snapshots can be
// thousands of rows, and the backend caps a stored thread at 5 MB. 1000 rows
// keeps cross-device exports useful without ever tripping that cap.
const SAVE_EXPORT_ROW_CAP = 1000
function trimForSave(msgs) {
  return (msgs || [])
    .filter((m) => !m.transient) // UI-only banners (e.g. load errors) never persist
    .map((m) =>
      m.exportRows?.length > SAVE_EXPORT_ROW_CAP
        ? { ...m, exportRows: m.exportRows.slice(0, SAVE_EXPORT_ROW_CAP), exportTruncated: true }
        : m,
    )
}

// Merge a fetched thread list (server metadata stubs, or a localStorage set)
// OVER the current in-memory threads, newest first, WITHOUT dropping a thread
// present on only one side — e.g. a chat the user started while the mount probe
// was still in flight. A plain setThreads(fetched) would REPLACE the array and
// silently lose that in-progress chat. Already-loaded message bodies are kept
// when the incoming copy is a stub.
function mergeThreads(current, incoming) {
  const byId = new Map((current || []).filter((t) => t?.id).map((t) => [t.id, t]))
  for (const t of incoming || []) {
    if (!t?.id) continue
    const have = byId.get(t.id)
    byId.set(
      t.id,
      have
        ? { ...t, messages: have.messages ?? t.messages, updatedAt: Math.max(t.updatedAt || 0, have.updatedAt || 0) }
        : t,
    )
  }
  return Array.from(byId.values()).sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
}

// Fallback: if the model ran a query but returned no prose, render the captured
// rows as a Markdown table so the CHAT always matches the EXPORT (never "no
// answer in chat but data in Excel"). Capped for readability; full data exports.
function rowsToMarkdown(columns, rows, limit = 30) {
  if (!rows?.length) return ''
  const cols = columns?.length ? columns : Object.keys(rows[0])
  const cell = (v) => (v === null || v === undefined ? '' : String(v)).replace(/\|/g, '\\|')
  const head = `| ${cols.join(' | ')} |`
  const sep = `| ${cols.map(() => '---').join(' | ')} |`
  const body = rows.slice(0, limit).map((r) => `| ${cols.map((c) => cell(r[c])).join(' | ')} |`).join('\n')
  const note = rows.length > limit ? `\n\n_Showing ${limit} of ${rows.length} rows — full data is in the export._` : ''
  return `${head}\n${sep}\n${body}${note}`
}

/*
 * useGlowstarRuntime — the single seam between the UI and the backend.
 *
 * Manages real chat threads plus the active conversation's streaming state.
 *
 * Thread persistence is SERVER-FIRST (backend /threads -> the history-db
 * Postgres container), so every device sees the same shared history:
 *   - mount: fetch the thread list (metadata only); one-time migration pushes
 *     any pre-existing localStorage history up to the server first.
 *   - open a thread: lazy-fetch its messages.
 *   - each turn: debounced whole-thread PUT (same shape localStorage used).
 *   - server unreachable / history disabled: quietly fall back to the old
 *     per-browser localStorage behaviour (chatStore).
 *
 * Returned shape:
 *   threads    { id, title, updatedAt }[]   (for the sidebar, newest first)
 *   activeId
 *   messages   { id, role, content, attachments? }[]
 *   isStreaming, status, loadingThread
 *   send(text, files), stop(), newChat(), selectThread(id), deleteThread(id)
 */
export function useGlowstarRuntime() {
  const [threads, setThreads] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [status, setStatus] = useState('')
  // True while a selected thread's messages are being fetched from the server;
  // send() is blocked meanwhile so a turn can never base itself on (and then
  // save) an empty snapshot of a thread that actually has history.
  const [loadingThread, setLoadingThread] = useState(false)

  const abortRef = useRef(null)
  const activeIdRef = useRef(null)
  const messagesRef = useRef([])
  const threadsRef = useRef([])
  // null = probing, true = server history, false = localStorage fallback.
  const serverModeRef = useRef(null)
  const saveTimersRef = useRef(new Map()) // thread id -> debounce timer
  const inFlightRef = useRef(new Set())   // ids whose PUT is on the wire right now
  const deletedIdsRef = useRef(new Set()) // ids deleted this session (never resurrect)

  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => { threadsRef.current = threads }, [threads])
  // localStorage mirror ONLY in fallback mode. In server mode the list holds
  // metadata-only stubs (messages lazy-loaded), so mirroring it would wipe the
  // real message bodies this browser still has stored locally.
  useEffect(() => {
    if (serverModeRef.current === false) saveThreads(threads)
  }, [threads])

  // Debounced server save of ONE thread (whole-thread PUT, like localStorage
  // saved whole threads). Reads the latest copy at fire time, so it naturally
  // skips threads deleted meanwhile and coalesces a turn's rapid updates.
  //
  // Durability: a FAILED save stashes the thread to the localStorage backup so
  // it isn't silently lost, and is retried on the next mount. A save that
  // SUCCEEDS clears that backup. If the thread was deleted while the PUT was in
  // flight, the row is re-deleted so a late save can't resurrect it.
  const schedulePersist = useCallback((id) => {
    if (serverModeRef.current !== true) return
    const timers = saveTimersRef.current
    clearTimeout(timers.get(id))
    timers.set(id, setTimeout(() => {
      timers.delete(id)
      if (deletedIdsRef.current.has(id)) return // deleted before we sent -> don't recreate
      const t = threadsRef.current.find((x) => x.id === id)
      if (!t || !t.messages) return // deleted (or never loaded) -> nothing to save
      const snapshot = { ...t, messages: trimForSave(t.messages) }
      inFlightRef.current.add(id) // so a tab-close DURING the PUT still backs it up (see flush)
      apiSaveThread(snapshot)
        .then(() => {
          inFlightRef.current.delete(id)
          clearUnsynced([id]) // confirmed on the server -> drop any local backup
          if (deletedIdsRef.current.has(id)) apiDeleteThread(id).catch(() => {}) // deleted mid-flight -> undo
        })
        .catch(() => {
          inFlightRef.current.delete(id)
          if (!deletedIdsRef.current.has(id)) stashUnsynced([snapshot]) // keep a copy to retry next load
        })
    }, 600))
  }, [])

  // Mount: probe the server store. Success -> server mode (+ one-time upload of
  // any old localStorage history). Failure -> per-browser localStorage mode.
  useEffect(() => {
    let cancelled = false

    // Resolve the probe. CRITICAL: we MERGE the fetched list over current state
    // rather than replacing it, so a chat the user started while the probe was
    // in flight is not dropped. Such a chat was persisted NOWHERE during the
    // probe (serverModeRef was still null, so schedulePersist bailed and the
    // localStorage mirror sat out too) -> once the mode is known we flush it.
    const finish = (mode, fetched) => {
      if (cancelled) return
      const carried = threadsRef.current.filter((t) => t.messages && t.messages.length)
      serverModeRef.current = mode
      setThreads((prev) => mergeThreads(prev, fetched))
      if (mode === true) {
        carried.forEach((t) => schedulePersist(t.id)) // persist probe-window chats now
      }
      // In fallback mode the localStorage-mirror effect persists the merged set.
    }

    ;(async () => {
      try {
        const list = await apiListThreads()
        if (cancelled) return
        let mergeList = list
        if (!isMigrated()) {
          const local = loadThreads()
          const known = new Set(list.map((t) => t.id))
          const toPush = local.filter((t) => t?.id && !known.has(t.id))
          // Set the mode BEFORE the (possibly slow) migration so any turn taken
          // during it persists normally instead of falling into the null window.
          serverModeRef.current = true
          if (toPush.length) {
            const results = await Promise.allSettled(
              toPush.map((t) => apiSaveThread({ ...t, messages: trimForSave(t.messages) })),
            )
            if (cancelled) return
            // Only mark migrated if EVERY push landed; a failed one is retried on
            // the next load instead of being silently orphaned (marked-done-but-lost).
            if (results.every((r) => r.status === 'fulfilled')) markMigrated()
            mergeList = [...list, ...toPush]
          } else {
            markMigrated()
          }
        }
        // Recover threads a prior session couldn't confirm-save (failed PUT, or
        // tab closed within the debounce): show them, retry the upload, and drop
        // the backup for whichever land. This is what stops those silent losses.
        const unsynced = loadUnsynced().filter((t) => !deletedIdsRef.current.has(t.id))
        finish(true, [...mergeList, ...unsynced])
        if (unsynced.length) {
          const pushed = []
          await Promise.allSettled(
            unsynced.map((t) =>
              apiSaveThread({ ...t, messages: trimForSave(t.messages) }).then(() => pushed.push(t.id)),
            ),
          )
          if (!cancelled) clearUnsynced(pushed)
        }
      } catch {
        finish(false, loadThreads())
      }
    })()
    return () => { cancelled = true }
  }, [schedulePersist])

  // Last-ditch durability: if the tab is closing (or hidden) while a save is
  // still debouncing, the async PUT won't complete — so synchronously stash the
  // pending threads to the localStorage backup, to be pushed on the next load.
  useEffect(() => {
    const flush = () => {
      if (serverModeRef.current !== true) return
      // Threads still debouncing (timer set) OR whose PUT is mid-flight — both
      // would be lost if the tab dies now, so back them up synchronously.
      const ids = new Set([...saveTimersRef.current.keys(), ...inFlightRef.current])
      const pending = Array.from(ids)
        .map((id) => threadsRef.current.find((t) => t.id === id))
        .filter((t) => t && t.messages && t.messages.length && !deletedIdsRef.current.has(t.id))
        .map((t) => ({ ...t, messages: trimForSave(t.messages) }))
      if (pending.length) stashUnsynced(pending)
    }
    const onVisibility = () => { if (document.visibilityState === 'hidden') flush() }
    window.addEventListener('pagehide', flush)
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      window.removeEventListener('pagehide', flush)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [])

  // Insert/replace a thread's messages and bump it to the top (newest first).
  // Used at the START of a turn, when the thread is guaranteed to exist/be new.
  const commitThread = useCallback((id, msgs, title) => {
    setThreads((prev) => {
      const now = Date.now()
      const existing = prev.find((t) => t.id === id)
      const entry = existing
        ? { ...existing, messages: msgs, updatedAt: now }
        : { id, title, messages: msgs, createdAt: now, updatedAt: now }
      return [entry, ...prev.filter((t) => t.id !== id)]
    })
    schedulePersist(id)
  }, [schedulePersist])

  // Update-only: persist a thread's final messages WITHOUT re-creating it if it
  // was deleted meanwhile. This is what a finishing/aborted turn uses, so a turn
  // that completes after its thread was deleted can't resurrect it (and can't
  // overwrite a DIFFERENT thread, because it targets `id` explicitly).
  const updateThreadMessages = useCallback((id, msgs) => {
    setThreads((prev) => {
      if (!prev.some((t) => t.id === id)) return prev // deleted -> stay deleted
      return prev.map((t) => (t.id === id ? { ...t, messages: msgs, updatedAt: Date.now() } : t))
    })
    // schedulePersist re-checks existence at fire time, so a deleted thread's
    // late save is a no-op here too.
    schedulePersist(id)
  }, [schedulePersist])

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    setStatus('')
  }, [])

  const newChat = useCallback(() => {
    stop()
    activeIdRef.current = null // sync so an in-flight turn's finally sees the switch
    setActiveId(null)
    setMessages([])
    setLoadingThread(false)
  }, [stop])

  const selectThread = useCallback((id) => {
    stop()
    const t = threadsRef.current.find((x) => x.id === id)
    if (!t) return
    activeIdRef.current = id // sync (see newChat)
    setActiveId(id)
    if (t.messages) {
      // Loaded already (fallback mode, or fetched earlier this visit).
      setMessages(t.messages)
      setLoadingThread(false)
      return
    }
    // Server mode: message bodies are lazy-loaded per thread. Everything after
    // the await is gated on the thread still being the active one, so switching
    // away mid-fetch can't paint another thread's screen.
    setMessages([])
    setLoadingThread(true)
    apiGetThread(id)
      .then((full) => {
        const msgs = Array.isArray(full.messages) ? full.messages : []
        setThreads((prev) => prev.map((x) => (x.id === id ? { ...x, messages: msgs } : x)))
        if (activeIdRef.current === id) {
          messagesRef.current = msgs
          setMessages(msgs)
        }
      })
      .catch(() => {
        if (activeIdRef.current === id) {
          // transient: shown but never persisted (filtered out by trimForSave,
          // and send() bases new turns on non-transient messages only).
          setMessages([{
            id: 'load-error',
            role: 'assistant',
            content: '⚠️ Could not load this chat from the server. Check the connection and reopen it.',
            ok: false,
            transient: true,
          }])
        }
      })
      .finally(() => {
        if (activeIdRef.current === id) setLoadingThread(false)
      })
  }, [stop])

  const deleteThread = useCallback((id) => {
    const wasActive = activeIdRef.current === id
    // If the thread being deleted is the one currently streaming, abort it first
    // so its request can't finish and re-save the deleted thread.
    if (wasActive) stop()
    // Mark deleted so any in-flight/pending save bails or undoes itself (a PUT
    // already on the wire re-deletes on completion; see schedulePersist).
    deletedIdsRef.current.add(id)
    const timers = saveTimersRef.current
    clearTimeout(timers.get(id))
    timers.delete(id)
    clearUnsynced([id]) // drop any local backup so it can't be recovered on next load
    setThreads((prev) => prev.filter((t) => t.id !== id))
    if (serverModeRef.current === true) {
      apiDeleteThread(id).catch(() => { /* best-effort; row stays until next delete */ })
    }
    if (wasActive) {
      activeIdRef.current = null // sync (see newChat)
      setActiveId(null)
      setMessages([])
      setLoadingThread(false)
    }
  }, [stop])

  const send = useCallback(
    async (text, files = []) => {
      const question = (text ?? '').trim()
      // loadingThread: this thread's history is still arriving from the server;
      // basing a turn on the empty placeholder would save over the real history.
      if ((!question && files.length === 0) || isStreaming || loadingThread) return

      // Ensure there's an active thread (create one on the first turn).
      let id = activeIdRef.current
      const isNew = !id
      if (!id) {
        id = newThreadId()
        setActiveId(id)
        activeIdRef.current = id
      }

      // Snapshot this thread's base messages BEFORE any await, so a navigation
      // during the upload can't rebase this turn onto another thread's messages.
      // (Minus transient UI banners, which must never enter the saved history.)
      const baseMsgs = messagesRef.current.filter((m) => !m.transient)

      // Best-effort upload of attachments to the backend /upload endpoint.
      const attachments = await Promise.all(
        files.map(async (att) => {
          try {
            const res = await uploadFile(att.file)
            return { name: att.name, kind: att.kind, fileId: res.file_id, uploaded: true }
          } catch {
            return { name: att.name, kind: att.kind, uploaded: false }
          }
        }),
      )

      // References for the backend to read+analyse (only successfully uploaded).
      const uploadedRefs = attachments
        .filter((a) => a.uploaded && a.fileId)
        .map((a) => ({ file_id: a.fileId, filename: a.name }))

      // If the user attached a file but typed nothing, give the backend a
      // sensible default prompt (its question field can't be empty).
      const queryText = question || (uploadedRefs.length ? 'Please analyse the attached file(s) and give me a summary.' : question)

      // Did the user navigate to ANOTHER thread during the upload await? If so,
      // this turn must not touch the shared on-screen state (that now belongs to
      // a different thread) — but it still runs and persists to ITS OWN thread.
      const stillActive = activeIdRef.current === id

      const userMsg = { id: `u-${Date.now()}`, role: 'user', content: question, attachments }
      const assistantId = `a-${Date.now()}`
      // `localMsgs` is THIS turn's own copy of its thread's messages, built on the
      // base snapshotted BEFORE the await. Persistence uses it (not the shared
      // messagesRef), so if the user switches away or starts a new chat mid-turn,
      // this turn still saves ITS thread's real content — never the now-empty or
      // other-thread global state. (Fixes the data-loss where switching chats
      // mid-answer wiped the original thread.)
      let localMsgs = [...baseMsgs, userMsg, { id: assistantId, role: 'assistant', content: '' }]
      const title = isNew ? makeTitle(question) : threads.find((t) => t.id === id)?.title || makeTitle(question)
      commitThread(id, localMsgs, title)  // persist to THIS turn's thread regardless

      if (stillActive) {
        messagesRef.current = localMsgs
        setMessages(localMsgs)
        setIsStreaming(true)
        setStatus('Analyzing your question…')
      }
      const controller = new AbortController()
      abortRef.current = controller

      // Does THIS turn still own what's on screen? True only when its thread is
      // the visible one AND no NEWER turn has taken over the live stream (a new
      // turn on the same thread sets abortRef to its own controller). Every
      // shared-UI write is gated on this, so a late callback from an abandoned
      // turn can never disturb whatever the user is now looking at — while
      // persistence still uses this turn's own localMsgs below.
      const ownsUI = () =>
        activeIdRef.current === id &&
        (abortRef.current === controller || abortRef.current === null)

      // Update this turn's assistant message. Always updates localMsgs (for
      // persistence); only reflects into the shared UI while this turn owns it.
      const patch = (fields) => {
        localMsgs = localMsgs.map((msg) =>
          msg.id === assistantId ? { ...msg, ...fields } : msg,
        )
        if (ownsUI()) {
          messagesRef.current = localMsgs
          setMessages(localMsgs)
        }
      }

      // Did the backend actually deliver a result or error? Set synchronously in
      // the callbacks so we never mistake a delivered answer for an interruption.
      let settled = false

      // Real backend: GlowStar text-to-SQL agent over SSE. The thread id is the
      // session id so each chat keeps its own follow-up memory. The agent sends
      // status updates, then one final result (answer + optional export query).
      // To go back to canned demo replies, swap streamQuestion for
      // streamMockReply from ./mockRuntime.
      try {
        await streamQuestion(queryText, id, {
          signal: controller.signal,
          attachments: uploadedRefs,
          onStatus: (msg) => { if (ownsUI()) setStatus(msg) },
          onResult: (data) => {
            settled = true
            if (ownsUI()) setStatus('')
            const answer = stripSql(data.answer)
            const cols = data.data_columns || []
            const rows = data.data_rows || []
            if (answer) {
              // Normal case: real prose answer (+ export if data-backed).
              patch({
                content: answer,
                ok: data.ok !== false,
                widgets: data.widgets || [],
                exportColumns: cols,
                exportRows: rows,
              })
            } else if (rows.length) {
              // Model gave no prose but the query returned data -> show the data
              // as a table so chat matches export. Export stays.
              patch({
                content: "Here's the data I found:\n\n" + rowsToMarkdown(cols, rows),
                ok: true,
                widgets: data.widgets || [],
                exportColumns: cols,
                exportRows: rows,
              })
            } else {
              // Nothing to show -> honest message, and NO export (chat==export).
              patch({
                content: "I couldn't produce an answer for that — please try again or rephrase it.",
                ok: false,
                exportColumns: [],
                exportRows: [],
              })
            }
          },
          onError: (msg) => {
            settled = true
            if (ownsUI()) setStatus('')
            patch({ content: `⚠️ ${msg}`, ok: false, exportColumns: [], exportRows: [] })
          },
        })
      } finally {
        const owns = ownsUI()
        // If this turn was interrupted with no answer, mark it "Stopped." —
        // always in localMsgs (so a closed/abandoned turn doesn't persist as an
        // eternal "thinking…" spinner), and in the UI too when this turn owns it.
        if (!settled) {
          localMsgs = localMsgs.map((m) =>
            m.id === assistantId
              ? { ...m, content: '_Stopped._', ok: false, exportColumns: [], exportRows: [] }
              : m,
          )
        }
        // Only clear the shared streaming state while this turn still owns the
        // screen — never clobber a newer turn the user has since started.
        if (owns) {
          abortRef.current = null
          setIsStreaming(false)
          setStatus('')
          messagesRef.current = localMsgs
          setMessages(localMsgs)
        }
        // Persist THIS turn's own messages to ITS thread (update-only, so a
        // deleted thread stays deleted and another thread is never touched).
        updateThreadMessages(id, localMsgs)
      }
    },
    [isStreaming, loadingThread, threads, commitThread, updateThreadMessages],
  )

  return {
    threads,
    activeId,
    messages,
    isStreaming,
    status,
    loadingThread,
    send,
    stop,
    newChat,
    selectThread,
    deleteThread,
  }
}
