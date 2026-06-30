import { isToday, isYesterday, differenceInCalendarDays } from 'date-fns'

// Bucket history items by updatedAt into Today / Yesterday / 7 days / Older.
// Returns an ordered array of { label, items } so the sidebar can render
// headers in chronological order and skip empty groups.
export function groupHistoryByDate(items, now) {
  const ref = now ?? Date.now()
  const buckets = { today: [], yesterday: [], week: [], older: [] }

  for (const it of [...items].sort((a, b) => b.updatedAt - a.updatedAt)) {
    const d = new Date(it.updatedAt)
    if (isToday(d)) buckets.today.push(it)
    else if (isYesterday(d)) buckets.yesterday.push(it)
    else if (differenceInCalendarDays(ref, d) <= 7) buckets.week.push(it)
    else buckets.older.push(it)
  }

  return [
    { label: 'Today', items: buckets.today },
    { label: 'Yesterday', items: buckets.yesterday },
    { label: '7 days', items: buckets.week },
    { label: 'Older', items: buckets.older },
  ].filter((g) => g.items.length > 0)
}
