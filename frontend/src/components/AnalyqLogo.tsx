type LogoProps = {
  className?: string
}

export function AnalyqWordmark({ className = '' }: LogoProps) {
  return (
    <span
      aria-label="Analyq"
      className={`analyq-wordmark relative inline-block whitespace-nowrap pb-[0.24em] pr-[0.3em] leading-none text-[#201e1a] ${className}`}
      role="img"
    >
      <span aria-hidden="true">analyq</span>
      <svg
        aria-hidden="true"
        className="absolute bottom-0 left-0 h-[0.4em] w-full"
        viewBox="0 0 240 34"
        preserveAspectRatio="none"
      >
        <path
          d="M2 24 H122 L148 30 L175 17 L192 27 L232 5"
          fill="none"
          stroke="currentColor"
          strokeLinejoin="miter"
          strokeWidth="2.5"
        />
        <path
          d="m228 3 10-2-5 10Z"
          fill="currentColor"
        />
      </svg>
    </span>
  )
}

export function AnalyqMark({ className = '' }: LogoProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      viewBox="0 0 48 48"
    >
      <text
        x="7"
        y="31"
        fill="currentColor"
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize="36"
        fontWeight="700"
      >
        a
      </text>
      <path
        d="M5 37 H18 L24 40 L31 34 L36 37 L44 28"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
      />
      <path
        d="m39 28 7-3-1 8Z"
        fill="currentColor"
      />
    </svg>
  )
}
