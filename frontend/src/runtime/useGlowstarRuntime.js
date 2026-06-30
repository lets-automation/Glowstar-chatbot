import { useCallback, useEffect, useRef, useState } from 'react'
import { streamQuestion, uploadFile } from '../api'
import { loadThreads, saveThreads, makeTitle } from '../lib/chatStore'

// Defensive: never surface raw SQL in a chat reply, even if the model embeds a
// fenced ```sql block. The query is intentionally hidden from responses.
function stripSql(text) {
  return (text || '').replace(/```sql[\s\S]*?```/gi, '').replace(/\n{3,}/g, '\n\n').trim()
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

  const stop = useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setIsStreaming(false)
    setStatus('')
  }, [])

  const newChat = useCallback(() => {
    stop()
    setActiveId(null)
    setMessages([])
  }, [stop])

  const selectThread = useCallback((id) => {
    stop()
    setThreads((prev) => {
      const t = prev.find((x) => x.id === id)
      if (t) {
        setActiveId(id)
        setMessages(t.messages || [])
      }
      return prev
    })
  }, [stop])

  const deleteThread = useCallback((id) => {
    setThreads((prev) => prev.filter((t) => t.id !== id))
    if (activeIdRef.current === id) {
      setActiveId(null)
      setMessages([])
    }
  }, [])

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

      const userMsg = { id: `u-${Date.now()}`, role: 'user', content: question, attachments }
      const assistantId = `a-${Date.now()}`
      const afterUser = [...messagesRef.current, userMsg, { id: assistantId, role: 'assistant', content: '' }]
      messagesRef.current = afterUser
      setMessages(afterUser)
      const title = isNew ? makeTitle(question) : threads.find((t) => t.id === id)?.title || makeTitle(question)
      commitThread(id, afterUser, title)

      setIsStreaming(true)
      setStatus('Analyzing your question…')
      const controller = new AbortController()
      abortRef.current = controller

      // Update the assistant message in place.
      const patch = (fields) => {
        setMessages((m) => {
          const next = m.map((msg) => (msg.id === assistantId ? { ...msg, ...fields } : msg))
          messagesRef.current = next
          return next
        })
      }

      // Real backend: GlowStar text-to-SQL agent over SSE. The thread id is the
      // session id so each chat keeps its own follow-up memory. The agent sends
      // status updates, then one final result (answer + optional export query).
      // To go back to canned demo replies, swap streamQuestion for
      // streamMockReply from ./mockRuntime.
      try {
        await streamQuestion(question, id, {
          signal: controller.signal,
          onStatus: (msg) => setStatus(msg),
          onResult: (data) => {
            setStatus('')
            patch({
              content: stripSql(data.answer) || 'No answer was returned.',
              exportQuery: data.export_query || null, // export shown only when present
            })
          },
          onError: (msg) => {
            setStatus('')
            patch({ content: `⚠️ ${msg}` })
          },
        })
      } finally {
        abortRef.current = null
        setIsStreaming(false)
        setStatus('')
        // If stopped before any answer arrived, don't leave a spinning bubble.
        const last = messagesRef.current.find((msg) => msg.id === assistantId)
        if (last && !last.content) patch({ content: '_Stopped._' })
        commitThread(id, messagesRef.current, title) // persist the final answer
      }
    },
    [isStreaming, threads, commitThread],
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
