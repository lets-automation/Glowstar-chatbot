import { useMemo } from 'react'
import { Plus, PanelLeftClose, Sparkles, Trash2 } from 'lucide-react'
import { cn } from '../lib/cn'
import { groupHistoryByDate } from '../lib/history'

/*
 * Sidebar — ~260px, collapsible. Logo, New chat, and the real chat history
 * grouped by date (Today / Yesterday / 7 days via date-fns over updatedAt).
 * Threads come from the runtime (persisted in chatStore).
 */
export default function Sidebar({ threads, activeId, onNewChat, onCollapse, onSelect, onDelete }) {
  const groups = useMemo(() => groupHistoryByDate(threads), [threads])

  return (
    <aside className="flex h-full w-[260px] flex-col border-r border-line-sidebar bg-sidebar">
      {/* Logo + collapse */}
      <div className="flex items-center justify-between px-4 pb-6 pt-4">
        <div className="flex items-center gap-2">
          <span className="grid h-7 w-7 place-items-center rounded-lg bg-gradient-to-br from-[#C9B6F5] to-[#A582EA] text-white">
            <Sparkles className="h-4 w-4" />
          </span>
          <span className="text-[0.98rem] font-semibold tracking-tight text-text">GlowStar</span>
        </div>
        <button
          type="button"
          onClick={onCollapse}
          aria-label="Collapse sidebar"
          className="grid h-7 w-7 place-items-center rounded-md text-text-muted transition hover:bg-[#F0F0F0] hover:text-text"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>

      {/* New chat (black, full width) */}
      <div className="px-3 pb-3 pt-1">
        <button
          type="button"
          onClick={onNewChat}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#111111] px-4 py-2.5 text-[0.86rem] font-medium text-white transition hover:bg-black/85"
        >
          <Plus className="h-4 w-4" />
          New chat
        </button>
      </div>

      {/* History — grouped by date */}
      <div className="scroll-quiet mt-1 flex-1 overflow-y-auto px-2 pb-3">
        {groups.map((group) => (
          <div key={group.label} className="mb-1.5">
            <div className="px-3 pb-1 pt-3 text-[0.68rem] font-medium uppercase tracking-wide text-text-muted">
              {group.label}
            </div>
            {group.items.map((item) => (
              <div
                key={item.id}
                className={cn(
                  'group flex items-center gap-1 rounded-lg pr-1 transition',
                  item.id === activeId ? 'bg-[#EFEAF7]' : 'hover:bg-[#F0F0F0]',
                )}
              >
                <button
                  type="button"
                  onClick={() => onSelect?.(item.id)}
                  className="min-w-0 flex-1 truncate px-3 py-1.5 text-left text-[0.83rem] text-text/85"
                  title={item.title}
                >
                  {item.title}
                </button>
                <button
                  type="button"
                  onClick={() => onDelete?.(item.id)}
                  aria-label="Delete chat"
                  className="grid h-6 w-6 flex-none place-items-center rounded text-text-muted opacity-0 transition hover:text-[#c0492f] group-hover:opacity-100"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            ))}
          </div>
        ))}
        {threads.length === 0 && (
          <p className="px-3 pt-6 text-center text-[0.8rem] leading-relaxed text-text-muted">
            No chats yet.<br />Start one to see it here.
          </p>
        )}
      </div>
    </aside>
  )
}
