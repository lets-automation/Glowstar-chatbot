import { useState } from 'react'
import { CalendarDays } from 'lucide-react'

/*
 * DateRangePicker — shown when the bot needs a period for a report (the backend
 * ends its reply with an ASKDATE: marker; see extract_askdate + the DATE PICKER
 * rule in tools.py).
 *
 * Built for a NON-TECHNICAL user (the client is a factory owner, staff often
 * write little English): the common periods are one tap, and "Custom" reveals two
 * native date inputs so the phone/desktop shows its own calendar. Picking a period
 * sends a plain-language follow-up question ("... from 1 Jun 2026 to 30 Jun 2026"),
 * so it flows through the SAME send() path as typing it by hand.
 */

// Local YYYY-MM-DD (never toISOString — that shifts the day in IST).
function iso(d) {
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

// "1 Jun 2026" — how a person says a date, for the question text.
function human(isoStr) {
  const [y, m, d] = isoStr.split('-').map(Number)
  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  return `${d} ${MONTHS[m - 1]} ${y}`
}

// The presets a factory manager actually asks for, newest-intent first.
function presets(today = new Date()) {
  const y = today.getFullYear()
  const m = today.getMonth()
  const startOfThisMonth = new Date(y, m, 1)
  const startOfLastMonth = new Date(y, m - 1, 1)
  const endOfLastMonth = new Date(y, m, 0)
  const last7 = new Date(y, m, today.getDate() - 6)
  return [
    { label: 'This month', from: iso(startOfThisMonth), to: iso(today) },
    { label: 'Last month', from: iso(startOfLastMonth), to: iso(endOfLastMonth) },
    { label: 'Last 7 days', from: iso(last7), to: iso(today) },
    { label: 'This year', from: iso(new Date(y, 0, 1)), to: iso(today) },
  ]
}

export default function DateRangePicker({ onPick, disabled = false }) {
  const [custom, setCustom] = useState(false)
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')

  function pick(fromIso, toIso) {
    if (!fromIso || !toIso) return
    onPick?.(`from ${human(fromIso)} to ${human(toIso)}`)
  }

  const customReady = from && to && from <= to
  const invalid = from && to && from > to

  return (
    <div className="mt-3 rounded-xl border border-line bg-[#FBFAFE] p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[0.78rem] font-medium text-text-muted">
        <CalendarDays className="h-4 w-4" />
        Choose the period
      </div>

      <div className="flex flex-wrap gap-2">
        {presets().map((p) => (
          <button
            key={p.label}
            type="button"
            disabled={disabled}
            onClick={() => pick(p.from, p.to)}
            className="inline-flex items-center rounded-full border border-accent bg-accent/10 px-3.5 py-1.5 text-[0.82rem] font-medium text-accent transition hover:bg-accent hover:text-white disabled:opacity-50"
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          disabled={disabled}
          onClick={() => setCustom((c) => !c)}
          className="inline-flex items-center rounded-full border border-dashed border-line bg-white px-3.5 py-1.5 text-[0.82rem] font-medium text-text-muted transition hover:border-accent hover:text-accent disabled:opacity-50"
        >
          Custom dates…
        </button>
      </div>

      {custom && (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-[0.72rem] text-text-muted">
            From
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => setFrom(e.target.value)}
              className="rounded-lg border border-line bg-white px-2.5 py-1.5 text-[0.85rem] text-text outline-none focus:border-accent"
            />
          </label>
          <label className="flex flex-col gap-1 text-[0.72rem] text-text-muted">
            To
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => setTo(e.target.value)}
              className="rounded-lg border border-line bg-white px-2.5 py-1.5 text-[0.85rem] text-text outline-none focus:border-accent"
            />
          </label>
          <button
            type="button"
            disabled={disabled || !customReady}
            onClick={() => pick(from, to)}
            className="rounded-lg bg-accent px-4 py-2 text-[0.82rem] font-medium text-white transition hover:opacity-90 disabled:opacity-40"
          >
            Show report
          </button>
          {invalid && (
            <span className="text-[0.75rem] text-[#8E2F2F]">
              The “From” date must be before the “To” date.
            </span>
          )}
        </div>
      )}
    </div>
  )
}
