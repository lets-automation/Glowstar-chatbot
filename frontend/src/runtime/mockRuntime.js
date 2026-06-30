/*
 * mockRuntime — a stand-in for the real LangGraph/SSE text-to-SQL backend.
 *
 * Mimics the production shape: a short natural-language answer, the generated
 * SQL, and the result as a Markdown table. Samples are grounded in the real
 * AasthaERP schema (jangad packets, incentive, fluorescence). Streams the
 * answer token-by-token so the UI's streaming path is exercised.
 *
 * ─────────────────────────────────────────────────────────────────────────
 * TODO: replace mockRuntime with the real runtime pointing at our gateway.
 *   - assistant-ui LangGraph adapter, or
 *   - the existing SSE endpoint in api.js: streamQuestion(question, sessionId…)
 * Only this module + useGlowstarRuntime.js change — components stay.
 * ─────────────────────────────────────────────────────────────────────────
 */

const SAMPLE = {
  jangad: {
    sql: `SELECT COUNT(*) AS packets_out, ROUND(SUM(Carat), 2) AS carat_out
FROM tblJangadPackets
WHERE IsReceived = 0;`,
    table: `| Packets Out | Carat Out |
|---|---|
| 4,812 | 9,371.55 |`,
    note: '4,812 packets are currently on jangad (IsReceived = 0) — still out on approval.',
  },
  incentive: {
    sql: `SELECT e.EmpName, ROUND(SUM(i.Amount), 0) AS total_incentive
FROM tblIncentiveAmount i
JOIN tblEmployee e ON e.ID = i.Emp_ID
GROUP BY e.EmpName
ORDER BY total_incentive DESC
LIMIT 5;`,
    table: `| Karigar | Total Incentive (₹) |
|---|---|
| Ramesh Patel | 2,14,500 |
| Jayesh Savaliya | 1,98,750 |
| Nilesh Dobariya | 1,76,200 |
| Hardik Vekariya | 1,69,400 |
| Mehul Kacha | 1,55,900 |`,
    note: 'Ramesh Patel leads on total incentive earned across all recorded periods.',
  },
  fluorescent: {
    sql: `SELECT Color, COUNT(*) AS stones
FROM tblPacket
WHERE Florecent <> 'NON'
GROUP BY Color
ORDER BY stones DESC;`,
    table: `| Colour | Fluorescent Stones |
|---|---|
| H | 3,128 |
| G | 2,744 |
| I | 2,510 |
| F | 1,902 |
| J | 1,431 |`,
    note: "Fluorescence is the misspelled 'Florecent' column; a fluorescent stone is any value other than 'NON'.",
  },
}

function pickSample(question) {
  const q = question.toLowerCase()
  if (q.includes('jangad') || q.includes('approval') || q.includes('out on')) return SAMPLE.jangad
  if (q.includes('incentive') || q.includes('karigar') || q.includes('employee') || q.includes('top')) return SAMPLE.incentive
  if (q.includes('fluorescent') || q.includes('florecent') || q.includes('colour') || q.includes('color')) return SAMPLE.fluorescent
  return SAMPLE.jangad
}

function buildReply(question, { attachments = [] }) {
  const s = pickSample(question)
  const lines = []
  if (attachments.length) {
    const names = attachments.map((a) => a.name).join(', ')
    lines.push(`Got your ${attachments.length > 1 ? 'attachments' : 'attachment'} (**${names}**). Here's what I found:`)
  } else {
    lines.push("Here's what I found:")
  }
  lines.push('', '```sql', s.sql, '```', '', s.table, '', s.note)
  return lines.join('\n')
}

// Stream the canned reply word-by-word. Honors an AbortSignal so the UI can
// stop generation. Returns the full text when complete.
export function streamMockReply(question, opts, { onToken, signal } = {}) {
  const full = buildReply(question, opts)
  const tokens = full.match(/\S+\s*/g) ?? [full]
  let i = 0

  return new Promise((resolve, reject) => {
    function tick() {
      if (signal?.aborted) return reject(new DOMException('Aborted', 'AbortError'))
      if (i >= tokens.length) return resolve(full)
      onToken?.(tokens[i])
      i += 1
      setTimeout(tick, 16 + (i % 5) * 6)
    }
    setTimeout(tick, 320)
  })
}
