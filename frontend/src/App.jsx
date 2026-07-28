import { useEffect, useRef, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Hero from './components/Hero'
import Thread from './components/Thread'
import { useGlowstarRuntime } from './runtime/useGlowstarRuntime'
import { attachmentProblem, describeAttachmentFailures } from './lib/attachments'
import { fetchSuggestions } from './api'

// Replace the last whitespace-delimited word of `text` with `name`.
function replaceLastWord(text, name) {
  return /(\S+)$/.test(text) ? text.replace(/(\S+)$/, name) : (text + name)
}

// Name shown in the top-right corner. No login screen — the chatbot runs
// standalone. (API access control lives in the backend behind AUTH_ENABLED,
// off by default; a CRM/SSO integration would supply identity there.)
const USER = {
  name: 'Chintan',
  avatar: 'https://api.dicebear.com/9.x/glass/svg?seed=Chintan&backgroundColor=A582EA,C9B6F5',
}

let attachSeq = 0

export default function App() {
  const rt = useGlowstarRuntime()
  const [input, setInput] = useState('')
  const [attachments, setAttachments] = useState([])
  // Why the last attachment / send was refused. Shown in the composer so an
  // upload can never fail invisibly.
  const [attachError, setAttachError] = useState('')
  // The message textarea, so a clarify "Something else…" button can focus it and
  // let the user type their own answer instead of picking an offered option.
  const composerInputRef = useRef(null)
  // Entity autocomplete: real names matching the word being typed, so the user
  // picks (e.g. "Fency") instead of mis-spelling it. Deterministic, from the DB.
  const [entitySuggestions, setEntitySuggestions] = useState([])
  const [collapsed, setCollapsed] = useState(false)
  const [isMobile, setIsMobile] = useState(false)

  // Below 860px the sidebar collapses and, when opened, floats as an overlay
  // instead of squeezing the main column.
  useEffect(() => {
    const mq = window.matchMedia('(max-width: 860px)')
    const apply = () => {
      setIsMobile(mq.matches)
      setCollapsed(mq.matches)
    }
    apply()
    mq.addEventListener('change', apply)
    return () => mq.removeEventListener('change', apply)
  }, [])

  // Debounced entity autocomplete on the last word being typed. Names come from
  // the DB (/suggest), so they can't be misspelled — the user taps a real one.
  useEffect(() => {
    const lastWord = (input.match(/(\S+)$/) || [])[1] || ''
    if (rt.isStreaming || lastWord.length < 2) {
      setEntitySuggestions([])
      return
    }
    const ctrl = new AbortController()
    const t = setTimeout(async () => {
      const s = await fetchSuggestions(lastWord, ctrl.signal)
      // Don't suggest the exact word they've already fully typed.
      setEntitySuggestions(s.filter((x) => x.name.toLowerCase() !== lastWord.toLowerCase()))
    }, 250)
    return () => { clearTimeout(t); ctrl.abort() }
  }, [input, rt.isStreaming])

  function pickSuggestion(name) {
    setInput((cur) => replaceLastWord(cur, name) + ' ')
    setEntitySuggestions([])
    requestAnimationFrame(() => composerInputRef.current?.focus())
  }

  const hasChat = rt.messages.length > 0

  // Reject unreadable/oversized files the moment they're picked, using the same
  // rules the server enforces — far better than accepting them here and failing
  // at send time (which is how the silent-upload bug went unnoticed).
  function addAttachments(files) {
    const accepted = []
    const refused = []
    files.forEach((file) => {
      const problem = attachmentProblem(file)
      if (problem) refused.push({ name: file.name, error: problem })
      else accepted.push(file)
    })

    if (accepted.length) {
      const next = accepted.map((file) => ({
        id: `att-${attachSeq++}`,
        file,
        name: file.name,
        kind: file.type.startsWith('image/') ? 'image' : 'file',
        preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
      }))
      setAttachments((a) => [...a, ...next])
    }
    setAttachError(refused.length ? describeAttachmentFailures(refused) : '')
  }

  function removeAttachment(id) {
    setAttachError('')
    setAttachments((a) => {
      const gone = a.find((x) => x.id === id)
      if (gone?.preview) URL.revokeObjectURL(gone.preview)
      return a.filter((x) => x.id !== id)
    })
  }

  async function submit() {
    if (!input.trim() && attachments.length === 0) return
    const text = input
    const files = attachments
    setInput('')
    setAttachments([])
    setAttachError('')

    const result = await rt.send(text, files)

    // Refused (an upload failed, or a turn was already streaming): put the
    // message and its files BACK so nothing the user typed is lost. The File
    // objects and preview URLs are still alive — clearing state above doesn't
    // revoke them. Don't clobber anything typed while the upload was running.
    if (result?.ok === false) {
      setInput((cur) => cur || text)
      setAttachments((cur) => (cur.length ? cur : files))
      if (result.message) setAttachError(result.message)
    } else {
      files.forEach((a) => a.preview && URL.revokeObjectURL(a.preview))
    }
  }

  function clearAttachments() {
    attachments.forEach((a) => a.preview && URL.revokeObjectURL(a.preview))
    setAttachments([])
    setAttachError('')
  }

  function newChat() {
    rt.newChat()
    setInput('')
    clearAttachments()
    if (isMobile) setCollapsed(true)
  }

  function selectThread(id) {
    rt.selectThread(id)
    setInput('')
    clearAttachments()
    if (isMobile) setCollapsed(true)
  }

  // Shared composer wiring for both the hero and the docked thread view.
  const composerProps = {
    value: input,
    onChange: (v) => {
      setInput(v)
      if (attachError) setAttachError('') // stale once they start fixing it
    },
    onSubmit: submit,
    isStreaming: rt.isStreaming,
    onStop: rt.stop,
    attachments,
    onAttach: addAttachments,
    onRemoveAttachment: removeAttachment,
    error: attachError,
    onDismissError: () => setAttachError(''),
    textareaRef: composerInputRef,
    suggestions: entitySuggestions,
    onPickSuggestion: pickSuggestion,
  }

  // Clarify "Something else…" — let the user type their own answer: focus the
  // message box (and clear any leftover text so they start fresh).
  function clarifyOther() {
    setInput('')
    // focus after the current render so the ref is attached and enabled
    requestAnimationFrame(() => composerInputRef.current?.focus())
  }

  return (
    <div className="relative flex h-screen w-full overflow-hidden bg-bg">
      {/* Soft lavender ambient bloom at the outer edges / right side */}
      <div
        className="pointer-events-none absolute inset-0 -z-0"
        style={{
          background:
            'radial-gradient(80% 60% at 100% 0%, var(--bg-ambient) 0%, transparent 55%), radial-gradient(70% 50% at 0% 100%, #EFE7F4 0%, transparent 60%)',
        }}
      />

      {/* Backdrop behind the mobile overlay sidebar */}
      {!collapsed && isMobile && (
        <div
          className="fixed inset-0 z-40 bg-black/30"
          onClick={() => setCollapsed(true)}
          aria-hidden="true"
        />
      )}

      {!collapsed && (
        <div className={isMobile ? 'fixed inset-y-0 left-0 z-50 shadow-xl' : 'relative z-10'}>
          <Sidebar
            threads={rt.threads}
            activeId={rt.activeId}
            onNewChat={newChat}
            onCollapse={() => setCollapsed(true)}
            onSelect={selectThread}
            onDelete={rt.deleteThread}
          />
        </div>
      )}

      <main className="relative z-10 flex min-w-0 flex-1 flex-col">
        <TopBar user={USER} collapsed={collapsed} onExpand={() => setCollapsed(false)} />

        <div className="min-h-0 flex-1">
          {hasChat ? (
            <Thread
              messages={rt.messages}
              isStreaming={rt.isStreaming}
              status={rt.status}
              composerProps={composerProps}
              onWidgetPrompt={(text) => rt.send(text)}
              onClarifyOther={clarifyOther}
            />
          ) : (
            <Hero userName={USER.name} composerProps={composerProps} onPickPrompt={setInput} />
          )}
        </div>
      </main>
    </div>
  )
}
