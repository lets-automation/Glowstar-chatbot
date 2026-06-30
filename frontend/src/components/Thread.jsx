import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, Paperclip, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react'
import Composer from './Composer'
import { exportData } from '../api'

// Markdown overrides: open links safely; let wide result tables scroll.
const MD_COMPONENTS = {
  a: ({ node, ...props }) => <a target="_blank" rel="noopener noreferrer" {...props} />,
  table: ({ node, ...props }) => <div className="table-wrap"><table {...props} /></div>,
}

/*
 * Thread — the active chat view. Messages scroll above a docked composer.
 * User turns are filled violet bubbles; assistant turns render the answer as
 * Markdown. An Export control appears only when the backend returned an
 * export query for that answer (i.e. there's tabular data worth exporting).
 */
export default function Thread({ messages, isStreaming, status, composerProps }) {
  const endRef = useRef(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, status])

  return (
    <div className="flex h-full flex-col">
      <div className="scroll-quiet flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-[820px] flex-col gap-5 px-4 py-8 sm:px-6">
          {messages.map((m) =>
            m.role === 'user' ? (
              <div key={m.id} className="flex flex-col items-end gap-1.5">
                {m.attachments?.length > 0 && (
                  <div className="flex flex-wrap justify-end gap-1.5">
                    {m.attachments.map((a, ai) => (
                      <span
                        key={ai}
                        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2 py-1 text-[0.74rem] text-text-muted"
                      >
                        <Paperclip className="h-3 w-3" />
                        {a.name}
                      </span>
                    ))}
                  </div>
                )}
                {m.content && (
                  <div className="max-w-[85%] rounded-2xl rounded-br-md bg-gradient-to-br from-[#A582EA] to-[#8B5CF6] px-4 py-2.5 text-[0.94rem] leading-relaxed text-white">
                    {m.content}
                  </div>
                )}
              </div>
            ) : (
              <div key={m.id} className="flex gap-3">
                <span className="mt-0.5 grid h-7 w-7 flex-none place-items-center rounded-full bg-gradient-to-br from-[#C9B6F5] to-[#A582EA] text-white">
                  <Sparkles className="h-3.5 w-3.5" />
                </span>
                <div className="min-w-0 flex-1 pt-0.5">
                  {m.content ? (
                    <>
                      <div className="markdown">
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                          {m.content}
                        </ReactMarkdown>
                      </div>
                      {m.exportQuery && <ExportControl query={m.exportQuery} />}
                    </>
                  ) : (
                    <div className="flex items-center gap-2 text-[0.86rem] text-text-muted">
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-accent" />
                      {status || 'Thinking…'}
                    </div>
                  )}
                </div>
              </div>
            ),
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* Docked composer */}
      <div className="border-t border-line bg-bg px-4 py-3.5 sm:px-6">
        <div className="mx-auto w-full max-w-[820px]">
          <Composer {...composerProps} />
        </div>
      </div>
    </div>
  )
}

// Conditional export — Excel / PDF. Only rendered when a message carries an
// export query. Downloads via the backend /export endpoint.
function ExportControl({ query }) {
  const [busy, setBusy] = useState(null) // 'excel' | 'pdf' | null

  async function run(format) {
    if (busy) return
    setBusy(format)
    try {
      await exportData(query, format)
    } catch {
      alert('Export failed — make sure the backend is running.')
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="mt-3 flex items-center gap-2">
      <span className="inline-flex items-center gap-1 text-[0.74rem] text-text-muted">
        <Download className="h-3.5 w-3.5" /> Export
      </span>
      <button
        type="button"
        onClick={() => run('excel')}
        disabled={!!busy}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-1 text-[0.76rem] font-medium text-text transition hover:border-accent hover:text-accent disabled:opacity-50"
      >
        {busy === 'excel' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileSpreadsheet className="h-3.5 w-3.5" />}
        Excel
      </button>
      <button
        type="button"
        onClick={() => run('pdf')}
        disabled={!!busy}
        className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-1 text-[0.76rem] font-medium text-text transition hover:border-accent hover:text-accent disabled:opacity-50"
      >
        {busy === 'pdf' ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <FileText className="h-3.5 w-3.5" />}
        PDF
      </button>
    </div>
  )
}
