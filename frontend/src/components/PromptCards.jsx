import { PackageOpen, Trophy, Gem } from 'lucide-react'
import { PROMPT_CARDS } from '../lib/data'

// Diamond-ERP starter cards. Clicking a card prefills the composer.
const ICONS = { jangad: PackageOpen, incentive: Trophy, fluorescent: Gem }

export default function PromptCards({ onPick }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
      {PROMPT_CARDS.map((card) => {
        const Icon = ICONS[card.id] ?? Gem
        return (
          <button
            key={card.id}
            type="button"
            onClick={() => onPick(card.prompt)}
            className="group flex flex-col gap-2 rounded-2xl border border-line bg-white p-5 text-left shadow-card transition hover:border-accent/50 hover:shadow-composer"
          >
            <Icon className="h-[22px] w-[22px] text-accent" />
            <div className="text-[0.95rem] font-semibold text-text">{card.title}</div>
            <div className="text-[0.82rem] leading-snug text-text-muted">{card.blurb}</div>
          </button>
        )
      })}
    </div>
  )
}
