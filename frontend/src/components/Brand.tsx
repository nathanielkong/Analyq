import { ChevronDown } from 'lucide-react'

import { AnalyqWordmark } from './AnalyqLogo'

export function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex min-w-0 items-center gap-3">
      <div className="min-w-0 flex-1">
        <AnalyqWordmark className={compact ? 'text-[1.7rem]' : 'text-[1.8rem]'} />
        {!compact ? (
          <p className="mt-1 text-[10px] text-[#91887c]">Pro Research</p>
        ) : null}
      </div>
      {!compact ? (
        <>
          <ChevronDown aria-hidden="true" className="text-[#8d857a]" size={15} />
        </>
      ) : null}
    </div>
  )
}
