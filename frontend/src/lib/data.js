// Static UI data: diamond-ERP starter cards.
// Questions are grounded in the real AasthaERP schema (see DATABASE_GUIDE.md),
// not the generic screenshot — each maps to actual tables and is answerable.
// (Chat history is no longer seeded here; it's real + persisted via chatStore.)

// Three starter cards. Clicking a card prefills the composer; the user sends it.
export const PROMPT_CARDS = [
  {
    id: 'jangad',
    title: 'Jangad Pending',
    blurb: 'Packets currently out on jangad (approval)',
    // tblJangadPackets WHERE IsReceived = 0
    prompt: 'How many packets are currently out on jangad?',
  },
  {
    id: 'incentive',
    title: 'Top Karigars',
    blurb: 'Top 5 employees by total incentive earned',
    // tblIncentiveAmount, grouped by employee
    prompt: 'Top 5 employees by total incentive earned.',
  },
  {
    id: 'fluorescent',
    title: 'Fluorescent Stones',
    blurb: 'Fluorescent stones broken down by colour',
    // Florecent <> 'NON', grouped by Color
    prompt: 'Total fluorescent stones broken down by colour.',
  },
]
