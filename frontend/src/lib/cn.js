import { clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

// Standard shadcn-style class combiner: conditional classes + Tailwind conflict
// resolution. e.g. cn('px-2', isActive && 'text-accent', props.className)
export function cn(...inputs) {
  return twMerge(clsx(inputs))
}
