import { useCallback, useEffect, useRef, useState } from 'react'
import { streamQuestion, uploadFile } from '../api'
import { loadThreads, saveThreads, makeTitle } from '../lib/chatStore'

// Defensive: never surface raw SQL in a chat reply, even if the model embeds a
// fenced ```sql block. The query is intentionally hidden from responses.
function stripSql(text) {
  return (text || '').replace(/```sql[\s\S]*?```/gi, '').replace(/\n{3,}/g, '\n\n').trim()
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
 * Manages real chat threads (persisted via chatStore) plus the active
 * conversation's streaming state. Today it streams from the mock runtime;
 * flipping to production is isolated to the `send` body below.
 *
 * Returned shape:
 *   threads    { id, title, updatedAt }[]   (for the sidebar, newest first)
 *   activeId
 *   messages   { id, role, content, attachments? }[]
 *   isStreaming, status
 *   send(text, files), stop(), newChat(), selectThread(id), deleteThread(id)
 */
export function useGlowstarRuntime() {
  const [threads, setThreads] = useState(() => loadThreads())
  const [activeId, setActiveId] = useState(null)
  const [messages, setMessages] = useState([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [status, setStatus] = useState('')

  const abortRef = useRef(null)
  const activeIdRef = useRef(null)
  const messagesRef = useRef([])

  useEffect(() => { activeIdRef.current = activeId }, [activeId])
  useEffect(() => { messagesRef.current = messages }, [messages])
  useEffect(() => { saveThreads(threads) }, [threads]) // persist on every change

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
  }, [])

  // Update-only: persist a thread's final messages WITHOUT re-creating it if it
  // was deleted meanwhile. This is what a finishing/aborted turn uses, so a turn
  // that completes after its thread was deleted can't resurrect it (and can't
  // overwrite a DIFFERENT thread, because it targets `id` explicitly).
  const updateThreadMessages = useCallback((id, msgs) => {
    setThreads((prev) => {
      if (!prev.some((t) => t.id === id)) return prev // deleted -> stay deleted
      return prev.map((t) => (t.id === id ? { ...t, messages: msgs, updatedAt: Date.now() } : t))
    })
  }, [])

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
  }, [stop])

  const selectThread = useCallback((id) => {
    stop()
    setThreads((prev) => {
      const t = prev.find((x) => x.id === id)
      if (t) {
        activeIdRef.current = id // sync (see newChat)
        setActiveId(id)
        setMessages(t.messages || [])
      }
      return prev
    })
  }, [stop])

  const deleteThread = useCallback((id) => {
    const wasActive = activeIdRef.current === id
    // If the thread being deleted is the one currently streaming, abort it first
    // so its request can't finish and re-save the deleted thread.
    if (wasActive) stop()
    setThreads((prev) => prev.filter((t) => t.id !== id))
    if (wasActive) {
      activeIdRef.current = null // sync (see newChat)
      setActiveId(null)
      setMessages([])
    }
  }, [stop])

  const send = useCallback(
    async (text, files = []) => {
      const question = (text ?? '').trim()
      if ((!question && files.length === 0) || isStreaming) return

      // Ensure there's an active thread (create one on the first turn).
      let id = activeIdRef.current
      const isNew = !id
      if (!id) {
        id = `t-${Date.now()}-${Math.floor(Math.random() * 1e4)}`
        setActiveId(id)
        activeIdRef.current = id
      }

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

      const userMsg = { id: `u-${Date.now()}`, role: 'user', content: question, attachments }
      const assistantId = `a-${Date.now()}`
      // `localMsgs` is THIS turn's own copy of its thread's messages. Persistence
      // uses it (not the shared messagesRef), so if the user switches away or
      // starts a new chat mid-stream, this turn still saves ITS thread's real
      // content — never the now-empty/other-thread global state. (Fixes the
      // data-loss where switching chats mid-answer wiped the original thread.)
      let localMsgs = [...messagesRef.current, userMsg, { id: assistantId, role: 'assistant', content: '' }]
      messagesRef.current = localMsgs
      setMessages(localMsgs)
      const title = isNew ? makeTitle(question) : threads.find((t) => t.id === id)?.title || makeTitle(question)
      commitThread(id, localMsgs, title)

      setIsStreaming(true)
      setStatus('Analyzing your question…')
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
    [isStreaming, threads, commitThread, updateThreadMessages],
  )

  return {
    threads,
    activeId,
    messages,
    isStreaming,
    status,
    send,
    stop,
    newChat,
    selectThread,
    deleteThread,
  }
}
