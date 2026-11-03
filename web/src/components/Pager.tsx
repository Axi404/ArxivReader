// 页码条：上一页、页码（跳过的显示成 …）、下一页；当前页是黑底。窄屏上当前页前后只留一页，排得下一行
import { useEffect, useState } from 'preact/hooks'
import { pageHref, pageItems } from '../lib/pages'
import { Icon } from './Icon'

const BOX = 'inline-grid h-[34px] min-w-[34px] place-items-center rounded-lg px-2 text-sm tabular-nums'

function useNarrow(): boolean {
  const [narrow, setNarrow] = useState(false)
  useEffect(() => {
    const media = window.matchMedia('(max-width: 760px)')
    const update = () => setNarrow(media.matches)
    update()
    media.addEventListener('change', update)
    return () => media.removeEventListener('change', update)
  }, [])
  return narrow
}

export function Pager({ page, pages, onChange }: { page: number; pages: number; onChange: (n: number) => void }) {
  const narrow = useNarrow()
  if (pages <= 1) return null

  // 普通点击在页面里换页；按着 Cmd/Ctrl/Shift 点的照常在新标签页打开
  const go = (e: MouseEvent, n: number) => {
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return
    e.preventDefault()
    onChange(n)
  }
  const arrow = (n: number, icon: 'left' | 'right', label: string) =>
    n >= 1 && n <= pages ? (
      <a href={pageHref(n)} onClick={(e) => go(e, n)} aria-label={label} class={`${BOX} border border-border bg-card hover:bg-secondary`}>
        <Icon name={icon} class="size-[15px]" />
      </a>
    ) : (
      <span aria-hidden="true" class={`${BOX} border border-border bg-card opacity-35`}>
        <Icon name={icon} class="size-[15px]" />
      </span>
    )

  return (
    <nav aria-label="分页" class="mt-4 flex items-center justify-center gap-1.5">
      {arrow(page - 1, 'left', '上一页')}
      {pageItems(page, pages, narrow ? 1 : 2).map((n, k) =>
        n === null ? (
          <span key={`gap${k}`} aria-hidden="true" class={`${BOX} text-faint`}>
            …
          </span>
        ) : n === page ? (
          <span key={n} aria-current="page" class={`${BOX} bg-foreground font-semibold text-background`}>
            {n}
          </span>
        ) : (
          <a key={n} href={pageHref(n)} onClick={(e) => go(e, n)} class={`${BOX} hover:bg-secondary`}>
            {n}
          </a>
        )
      )}
      {arrow(page + 1, 'right', '下一页')}
    </nav>
  )
}
