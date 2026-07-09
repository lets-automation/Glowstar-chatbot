import { useEffect, useState } from 'react'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import Hero from './components/Hero'
import Thread from './components/Thread'
import { useGlowstarRuntime } from './runtime/useGlowstarRuntime'

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

  const hasChat = rt.messages.length > 0

  function addAttachments(files) {
    const next = files.map((file) => ({
      id: `att-${attachSeq++}`,
      file,
      name: file.name,
      kind: file.type.startsWith('image/') ? 'image' : 'file',
      preview: file.type.startsWith('image/') ? URL.createObjectURL(file) : null,
    }))
    setAttachments((a) => [...a, ...next])
  }

  function removeAttachment(id) {
    setAttachments((a) => {
      const gone = a.find((x) => x.id === id)
      if (gone?.preview) URL.revokeObjectURL(gone.preview)
      return a.filter((x) => x.id !== id)
    })
  }

  function submit() {
    if (!input.trim() && attachments.length === 0) return
    const text = input
    const files = attachments
    setInput('')
    setAttachments([])
    rt.send(text, files)
  }

  function clearAttachments() {
    attachments.forEach((a) => a.preview && URL.revokeObjectURL(a.preview))
    setAttachments([])
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
    onChange: setInput,
    onSubmit: submit,
    isStreaming: rt.isStreaming,
    onStop: rt.stop,
    attachments,
    onAttach: addAttachments,
    onRemoveAttachment: removeAttachment,
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
            />
          ) : (
            <Hero userName={USER.name} composerProps={composerProps} onPickPrompt={setInput} />
          )}
        </div>
      </main>
    </div>
  )
}
