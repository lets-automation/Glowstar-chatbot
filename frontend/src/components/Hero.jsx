import Orb from './Orb'
import Composer from './Composer'
import PromptCards from './PromptCards'

/*
 * Hero — the centered empty state: the moving 3D orb, the gradient greeting,
 * the composer, and the three diamond-domain prompt cards. Scales down on
 * phones and up on wide desktops; the outer wrapper scrolls so nothing clips
 * on short screens.
 */
export default function Hero({ userName, composerProps, onPickPrompt }) {
  return (
    <div className="scroll-quiet h-full overflow-y-auto">
      <div className="flex min-h-full items-center justify-center px-4 py-8 sm:px-6">
        <div className="flex w-full max-w-[680px] flex-col items-center lg:max-w-[780px] xl:max-w-[880px]">
          {/* 3D orb — responsive box, the canvas fills it (orb has its own motion) */}
          <div className="h-44 w-44 sm:h-56 sm:w-56 xl:h-64 xl:w-64">
            <Orb />
          </div>

          {/* Greeting */}
          <h1 className="mt-2 bg-greeting-gradient bg-clip-text text-2xl font-semibold tracking-tight text-transparent sm:text-3xl xl:text-4xl">
            Hello, {userName}
          </h1>
          <h2 className="mt-1 text-center text-2xl font-bold tracking-tight text-text sm:text-3xl xl:text-4xl">
            How can I assist you today?
          </h2>

          {/* Composer */}
          <div className="mt-6 w-full sm:mt-8">
            <Composer {...composerProps} size="lg" />
          </div>

          {/* Prompt cards */}
          <div className="mt-4 w-full">
            <PromptCards onPick={onPickPrompt} />
          </div>
        </div>
      </div>
    </div>
  )
}
