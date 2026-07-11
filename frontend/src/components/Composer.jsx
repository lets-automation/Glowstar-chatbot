import { useRef } from 'react'
import { Image as ImageIcon, Paperclip, ArrowUp, Square, X, FileText } from 'lucide-react'
import { cn } from '../lib/cn'

// Attachments are DISABLED in the UI until the silent upload-failure bug is
// fixed (a failed upload sends the question WITHOUT the file while the chip
// stays visible — the answer looks wrong with no hint why). Flip to true to
// bring the image/file pickers back; the whole pipeline behind them is intact.
const ATTACHMENTS_ENABLED = false

/*
 * Composer — the input surface, shared by the hero empty-state and the docked
 * active-chat view. Taller text area; two working pickers (image + file) that
 * attach to the message as removable chips; circular gradient send button.
 *
 * Controlled by the parent: value/onChange/onSubmit + attachments/onAttach/
 * onRemoveAttachment. Files are forwarded on submit (see useGlowstarRuntime).
 */
export default function Composer({
  value,
  onChange,
  onSubmit,
  isStreaming,
  onStop,
  attachments = [],
  onAttach,
  onRemoveAttachment,
  size = 'md',
}) {
  const imageInput = useRef(null)
  const fileInput = useRef(null)
  const lg = size === 'lg'

  function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSubmit()
    }
  }

  function pick(e) {
    const files = Array.from(e.target.files ?? [])
    if (files.length) onAttach?.(files)
    e.target.value = '' // allow re-picking the same file
  }

  const canSend = value.trim().length > 0 || attachments.length > 0

  return (
    <div className="w-full rounded-3xl border border-line bg-white shadow-composer transition-colors focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
      {/* Hidden native pickers */}
      <input ref={imageInput} type="file" accept="image/*" multiple hidden onChange={pick} />
      <input ref={fileInput} type="file" multiple hidden onChange={pick} />

      {/* Attachment chips */}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 px-5 pt-4">
          {attachments.map((att) => (
            <span
              key={att.id}
              className="inline-flex items-center gap-2 rounded-lg border border-line bg-[#FBFAFE] py-1 pl-1.5 pr-2 text-[0.78rem] text-text"
            >
              {att.preview ? (
                <img src={att.preview} alt="" className="h-7 w-7 rounded object-cover" />
              ) : (
                <span className="grid h-7 w-7 place-items-center rounded bg-[#F1EAFE] text-accent">
                  <FileText className="h-4 w-4" />
                </span>
              )}
              <span className="max-w-[160px] truncate">{att.name}</span>
              <button
                type="button"
                onClick={() => onRemoveAttachment?.(att.id)}
                aria-label={`Remove ${att.name}`}
                className="grid h-5 w-5 place-items-center rounded text-text-muted hover:bg-[#F0F0F0] hover:text-text"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Input */}
      <div className={cn('px-5', lg ? 'pt-5' : 'pt-4')}>
        <textarea
          rows={lg ? 4 : 3}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask me anything…"
          className={cn(
            'w-full resize-none bg-transparent text-text outline-none placeholder:text-text-muted',
            lg ? 'min-h-[88px] max-h-72 text-[1.02rem] leading-8 sm:min-h-[120px]' : 'min-h-[72px] max-h-56 text-[1rem] leading-7',
          )}
        />
      </div>

      <div className={cn('flex items-center justify-between gap-2 px-4 pt-1', lg ? 'pb-5' : 'pb-4')}>
        {/* Left: image + file pickers (hidden while ATTACHMENTS_ENABLED=false) */}
        <div className="flex items-center gap-1.5">
          {ATTACHMENTS_ENABLED && (
            <>
              <ToolButton lg={lg} label="Attach image" onClick={() => imageInput.current?.click()}>
                <ImageIcon className={lg ? 'h-5 w-5' : 'h-[18px] w-[18px]'} />
              </ToolButton>
              <ToolButton lg={lg} label="Attach file" onClick={() => fileInput.current?.click()}>
                <Paperclip className={lg ? 'h-5 w-5' : 'h-[18px] w-[18px]'} />
              </ToolButton>
            </>
          )}
        </div>

        {/* Right: send / stop */}
        {isStreaming ? (
          <button
            type="button"
            onClick={onStop}
            aria-label="Stop generating"
            className={cn(
              'grid place-items-center rounded-full bg-accent-strong text-white transition hover:opacity-90',
              lg ? 'h-12 w-12' : 'h-11 w-11',
            )}
          >
            <Square className={lg ? 'h-[18px] w-[18px] fill-current' : 'h-4 w-4 fill-current'} />
          </button>
        ) : (
          <button
            type="button"
            onClick={onSubmit}
            disabled={!canSend}
            aria-label="Send message"
            className={cn(
              'grid place-items-center rounded-full bg-send-gradient text-white shadow-sm transition enabled:hover:brightness-105 disabled:opacity-40',
              lg ? 'h-12 w-12' : 'h-11 w-11',
            )}
          >
            <ArrowUp className={lg ? 'h-6 w-6' : 'h-5 w-5'} />
          </button>
        )}
      </div>
    </div>
  )
}

function ToolButton({ children, label, onClick, lg }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        'grid place-items-center rounded-full text-text-muted transition hover:bg-[#F4F0FB] hover:text-accent',
        lg ? 'h-11 w-11' : 'h-10 w-10',
      )}
    >
      {children}
    </button>
  )
}
