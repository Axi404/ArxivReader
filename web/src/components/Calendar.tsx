// 日历：有数据的日子可以点，当前这一天是黑底；左右翻有数据的月份
import { useMemo, useState } from 'preact/hooks'
import { Icon } from './Icon'

const DOW = ['一', '二', '三', '四', '五', '六', '日']

export function Calendar({ dates, current }: { dates: string[]; current: string }) {
  const available = useMemo(() => new Set(dates), [dates])
  const months = useMemo(() => [...new Set(dates.map((d) => d.slice(0, 7)))].sort(), [dates])
  const [month, setMonth] = useState(current.slice(0, 7))
  const k = months.indexOf(month)
  const [y, m] = month.split('-').map(Number)
  const pad = (new Date(y, m - 1, 1).getDay() + 6) % 7
  const days = new Date(y, m, 0).getDate()

  const step = (d: number) => {
    const next = months[k + d]
    if (next) setMonth(next)
  }

  return (
    <div class="w-[284px] px-3.5 pb-2.5 pt-3">
      <div class="mb-1 flex items-center gap-0.5">
        <span class="flex-1 pl-1 text-sm font-semibold tabular-nums">{`${y} 年 ${m} 月`}</span>
        {(
          [
            [-1, 'left', '上个月'],
            [1, 'right', '下个月']
          ] as const
        ).map(([d, icon, label]) => (
          <button
            key={d}
            type="button"
            aria-label={label}
            disabled={!months[k + d]}
            onClick={() => step(d)}
            class="grid size-7 place-items-center rounded-lg text-muted-foreground enabled:hover:bg-secondary enabled:hover:text-foreground disabled:cursor-default disabled:opacity-30"
          >
            <Icon name={icon} class="size-[15px]" />
          </button>
        ))}
      </div>
      <div class="grid grid-cols-[repeat(7,36px)] justify-between gap-y-0.5">
        {DOW.map((w) => (
          <span key={w} class="grid h-7 place-items-center text-xs text-faint">
            {w}
          </span>
        ))}
        {Array.from({ length: pad }, (_, i) => (
          <span key={`pad${i}`} />
        ))}
        {Array.from({ length: days }, (_, i) => {
          const d = i + 1
          const iso = `${month}-${String(d).padStart(2, '0')}`
          const base = 'grid size-9 place-items-center rounded-[10px] text-sm tabular-nums'
          if (iso === current) return <span key={iso} class={`${base} bg-foreground font-semibold text-background`}>{d}</span>
          if (available.has(iso))
            return (
              <a key={iso} href={`/daily/${iso}`} class={`${base} hover:bg-secondary`}>
                {d}
              </a>
            )
          return (
            <span key={iso} class={`${base} text-faint opacity-45`}>
              {d}
            </span>
          )
        })}
      </div>
    </div>
  )
}
