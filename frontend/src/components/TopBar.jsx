import { PanelLeftOpen } from 'lucide-react'

/*
 * TopBar — minimal. Sidebar re-open button on the left (when collapsed); the
 * signed-in user's name in the right corner (name only — no email, no logout,
 * no model selector / share / export / upgrade).
 */
export default function TopBar({ user, collapsed, onExpand }) {
  return (
    <header className="flex h-14 items-center justify-between border-b border-line bg-bg/80 px-4 backdrop-blur">
      <div className="flex items-center gap-2">
        {collapsed && (
          <button
            type="button"
            onClick={onExpand}
            aria-label="Open sidebar"
            className="grid h-8 w-8 place-items-center rounded-md text-text-muted transition hover:bg-[#F0F0F0] hover:text-text"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        )}
      </div>

      <div className="flex items-center gap-2.5">
        <span className="text-[0.9rem] font-medium text-text">{user.name}</span>
        <img src={user.avatar} alt="" className="h-8 w-8 rounded-full object-cover" />
      </div>
    </header>
  )
}
