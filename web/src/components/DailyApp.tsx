// 每日页：从 /api/daily/<日期> 取数据，按分类列出；右边是目录
import { useEffect, useMemo, useRef, useState } from 'preact/hooks'
import { fetchDaily, fetchDates, NotFound } from '../lib/api'
import { dateFromPath, weekdayOf } from '../lib/dates'
import { matchCount, prefs, query } from '../lib/store'
import { buildDaily, matches, searchTerms, type CategoryView } from '../lib/view'
import { Calendar } from './Calendar'
import { CategorySection } from './CategorySection'
import { Icon } from './Icon'
import { Popover } from './Popover'
import { Shell } from './Shell'
import { Toc, type TocItem } from './Toc'

type Load = { state: 'loading' } | { state: 'missing' } | { state: 'error'; message: string } | { state: 'ok'; cats: CategoryView[] }

function NavButton({ to, icon, label }: { to: string | null; icon: 'left' | 'right'; label: string }) {
  const cls = 'inline-grid size-[34px] place-items-center rounded-lg border border-border bg-card'
  if (!to)
    return (
      <span class={`${cls} opacity-35`} aria-hidden="true">
        <Icon name={icon} />
      </span>
    )
  return (
    <a class={`${cls} hover:bg-secondary`} href={`/daily/${to}`} aria-label={label} title={to}>
      <Icon name={icon} />
    </a>
  )
}

export function DailyApp() {
  // 日期在地址里；构建时没有地址，所以挂上以后再读
  const [date, setDate] = useState<string | null>(null)
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [dates, setDates] = useState<string[]>([])
  const [calOpen, setCalOpen] = useState(false)
  const dateBtn = useRef<HTMLButtonElement>(null)

  useEffect(() => setDate(dateFromPath(window.location.pathname) ?? ''), [])

  useEffect(() => {
    if (date === null) return
    if (date) document.title = `${date} · arXiv Reader`
    if (!date) return setLoad({ state: 'missing' })
    fetchDaily(date).then(
      (file) => setLoad({ state: 'ok', cats: buildDaily(file) }),
      (err) => setLoad(err instanceof NotFound ? { state: 'missing' } : { state: 'error', message: String(err.message ?? err) })
    )
    fetchDates().then(setDates, () => setDates([]))
  }, [date])

  // 数据出来以后，带着 #分类 打开的要跳过去
  useEffect(() => {
    if (load.state !== 'ok' || !window.location.hash) return
    document.getElementById(decodeURIComponent(window.location.hash.slice(1)))?.scrollIntoView()
  }, [load.state])

  const scope = prefs.value.scope
  const terms = searchTerms(query.value)

  const shown = useMemo(() => {
    if (load.state !== 'ok') return []
    return load.cats.map((cat) => ({
      cat,
      news: terms.length ? cat.new.filter((p) => matches(p, terms)) : cat.new,
      crosses: terms.length ? cat.cross.filter((p) => matches(p, terms)) : cat.cross
    }))
  }, [load, query.value])

  const totals = shown.reduce((t, s) => ({ new: t.new + s.news.length, cross: t.cross + s.crosses.length }), { new: 0, cross: 0 })
  const inScope = (scope !== 'cross' ? totals.new : 0) + (scope !== 'primary' ? totals.cross : 0)
  useEffect(() => {
    matchCount.value = inScope
  }, [inScope])

  const toc: TocItem[] = useMemo(() => {
    const items: TocItem[] = []
    for (const s of shown) {
      items.push({ id: s.cat.anchor, label: s.cat.code, count: scope === 'cross' ? s.crosses.length : s.news.length })
      if (scope === 'all' && s.cat.cross.length) items.push({ id: `${s.cat.anchor}-cross`, label: 'cross-list', count: s.crosses.length, sub: true })
    }
    return items
  }, [shown, scope])

  const day = date ?? ''
  const i = dates.indexOf(day)
  const prev = i >= 0 && i < dates.length - 1 ? dates[i + 1] : null
  const next = i > 0 ? dates[i - 1] : null

  return (
    <Shell daily>
      <div class="relative">
        <div class="mt-[18px] flex items-center gap-2">
          <h1 class="m-0 min-w-0 flex-1 text-base font-normal">
            <button
              ref={dateBtn}
              type="button"
              aria-label="选日期"
              onClick={() => setCalOpen(!calOpen)}
              class="group inline-flex items-baseline gap-2.5 whitespace-nowrap text-3xl max-[760px]:text-2xl"
            >
              {day}
              <span class="text-lg text-faint max-[760px]:text-base">{day && weekdayOf(day)}</span>
              <Icon name="down" class={`size-[18px] self-center text-faint transition-transform group-hover:text-foreground ${calOpen ? 'rotate-180' : ''}`} />
            </button>
          </h1>
          <NavButton to={prev} icon="left" label="前一天" />
          <NavButton to={next} icon="right" label="后一天" />
        </div>
        <Popover anchor={dateBtn} open={calOpen} onClose={() => setCalOpen(false)} align="left" label="日历">
          <Calendar dates={dates} current={day} />
        </Popover>

        {load.state === 'ok' && (
          <>
            <div class="mt-3 flex flex-wrap gap-x-[18px] gap-y-1.5 text-sm text-faint">
              {scope !== 'cross' && (
                <span>
                  新提交 <b class="font-semibold tabular-nums text-foreground">{totals.new}</b>
                </span>
              )}
              {scope !== 'primary' && (
                <span>
                  cross-list <b class="font-semibold tabular-nums text-foreground">{totals.cross}</b>
                </span>
              )}
            </div>
            <hr class="mt-[22px] w-[34%] border-0 border-t border-border" />
            {shown.map((s) => (
              <CategorySection key={s.cat.code} cat={s.cat} news={s.news} crosses={s.crosses} scope={scope} date={day} />
            ))}
            <div class="absolute bottom-0 left-[calc(100%+48px)] top-0 hidden w-[176px] min-[1280px]:block">
              <Toc items={toc} />
            </div>
          </>
        )}
        {load.state === 'missing' && <p class="mt-10 text-muted-foreground">没有 {day || '这一天'} 的数据</p>}
        {load.state === 'error' && <p class="mt-10 text-muted-foreground">加载失败：{load.message}</p>}
      </div>
    </Shell>
  )
}
