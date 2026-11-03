// 首页：最新一期、统计、按月的归档（左边粗标题、右边卡片，和博客首页一样）；归档分页，第几页记在地址里
import type { ComponentChildren } from 'preact'
import { useEffect, useRef, useState } from 'preact/hooks'
import { fetchOverview } from '../lib/api'
import { categoryName } from '../lib/categories'
import { monthLabel, weekdayOf } from '../lib/dates'
import { pageFromSearch, pageHref } from '../lib/pages'
import { prefs, prefsReady } from '../lib/store'
import type { Overview } from '../lib/types'
import { Icon, type IconName } from './Icon'
import { Pager } from './Pager'
import { Shell } from './Shell'
import { Card } from './ui'

function Block({ id, title, children }: { id?: string; title: string; children: ComponentChildren }) {
  return (
    <section id={id} class="mt-11 grid grid-cols-[150px_minmax(0,1fr)] gap-x-7 first:mt-[18px] max-[760px]:mt-8 max-[760px]:grid-cols-1">
      <div class="pt-2.5 max-[760px]:pb-3 max-[760px]:pt-0">
        <h2 class="m-0 text-xl font-semibold">{title}</h2>
      </div>
      <div class="min-w-0">{children}</div>
    </section>
  )
}

function Stat({ icon, n, label }: { icon: IconName; n: number; label: string }) {
  return (
    <Card class="px-2.5 pb-3.5 pt-[18px] text-center">
      <Icon name={icon} class="mx-auto size-[17px] text-muted-foreground" />
      <div class="mt-1.5 text-2xl font-bold tabular-nums">{n}</div>
      <div class="text-sm text-muted-foreground">{label}</div>
    </Card>
  )
}

export function HomeApp() {
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState('')
  const [page, setPage] = useState(1)

  useEffect(() => {
    fetchOverview().then(setData, (e) => setError(String(e.message ?? e)))
    const read = () => setPage(pageFromSearch(window.location.search))
    read()
    window.addEventListener('popstate', read)
    return () => window.removeEventListener('popstate', read)
  }, [])

  const size = prefs.value.pageSize
  const days = data?.days ?? []
  const pages = Math.max(1, Math.ceil(days.length / size))
  const cur = Math.min(page, pages)

  // 改了每页几天：换到原来那一页第一天所在的页。只管设置读进来以后的改动（读进来之前用的是默认值）
  const lastSize = useRef<number | null>(null)
  useEffect(() => {
    if (!prefsReady.value) return
    const now = prefs.value.pageSize
    const before = lastSize.current
    lastSize.current = now
    if (before === null || before === now) return
    const first = (Math.min(page, Math.max(1, Math.ceil(days.length / before))) - 1) * before
    const n = Math.floor(first / now) + 1
    setPage(n)
    history.replaceState(null, '', pageHref(n))
  }, [size, prefsReady.value])

  // 地址里的页数超出了范围（比如 ?page=99），改成最后一页
  useEffect(() => {
    if (data && prefsReady.value && page !== cur) {
      setPage(cur)
      history.replaceState(null, '', pageHref(cur))
    }
  }, [data, page, cur])

  const goPage = (n: number) => {
    setPage(n)
    history.pushState(null, '', pageHref(n))
    // 在页码条那里点的，换页以后回到归档的开头
    const archive = document.getElementById('archive')
    if (archive && archive.getBoundingClientRect().top < 90) archive.scrollIntoView({ block: 'start' })
  }

  const latest = data?.days[0]
  const months: { month: string; days: Overview['days'] }[] = []
  for (const d of days.slice((cur - 1) * size, cur * size)) {
    const m = d.date.slice(0, 7)
    if (months[months.length - 1]?.month !== m) months.push({ month: m, days: [] })
    months[months.length - 1].days.push(d)
  }

  return (
    <Shell daily={false}>
      {error && <p class="mt-10 text-muted-foreground">加载失败：{error}</p>}
      {latest && (
        <Block title="最新">
          <Card class="px-[22px] py-[18px]">
            <div class="flex items-center gap-6 max-[760px]:flex-col max-[760px]:items-stretch max-[760px]:gap-3.5">
              <div class="min-w-0 flex-1">
                <span class="text-lg font-semibold">{latest.date}</span>
                <span class="ml-2.5 text-sm text-faint">{weekdayOf(latest.date)}</span>
              </div>
              <a
                href={`/daily/${latest.date}`}
                class="inline-flex h-[34px] items-center gap-1.5 self-start whitespace-nowrap rounded-lg border border-border bg-secondary px-3.5 text-sm hover:border-foreground/35 hover:bg-muted"
              >
                阅读
                <Icon name="right" class="size-3.5" />
              </a>
            </div>
            {latest.summary && (
              <table class="mt-2.5 w-full border-collapse text-sm">
                <thead>
                  <tr class="text-faint">
                    <th class="pb-1.5 text-left font-normal" />
                    {['新提交', 'cross-list', '已翻译'].map((h) => (
                      <th key={h} class="w-[22%] pb-1.5 text-right font-normal">
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {latest.summary.categories.map((c) => (
                    <tr key={c.code} class="border-t border-border">
                      <td class="py-[7px]">
                        <a href={`/daily/${latest.date}#cat-${c.code.replace('.', '-')}`}>{c.code}</a>
                        <span class="ml-2 text-faint max-[760px]:hidden">{categoryName(c.code)}</span>
                      </td>
                      <td class="py-[7px] text-right tabular-nums">{c.new}</td>
                      <td class="py-[7px] text-right tabular-nums">{c.cross}</td>
                      <td class="py-[7px] text-right tabular-nums">{c.translated}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        </Block>
      )}
      {data && (
        <>
          <Block title="统计">
            <div class="grid grid-cols-4 gap-3.5 max-[760px]:grid-cols-2">
              <Stat icon="calendar" n={data.stats.days} label="天数" />
              <Stat icon="file" n={data.stats.papers} label="论文" />
              <Stat icon="eye" n={data.traffic.daily} label="今日访问" />
              <Stat icon="clock" n={data.traffic.total} label="累计访问" />
            </div>
          </Block>
          <Block id="archive" title="归档">
            <Card class="px-[22px] py-1.5">
              {months.map(({ month, days }) => (
                <div key={month}>
                  <h4 class="mb-0.5 mt-4 text-sm font-semibold text-faint first:mt-2">{monthLabel(month)}</h4>
                  {days.map((d) => (
                    <a key={d.date} href={`/daily/${d.date}`} class="group flex items-center gap-3.5 border-t border-border py-[9px] [h4+&]:border-t-0">
                      <span class="tabular-nums group-hover:underline group-hover:underline-offset-[3px]">{d.date}</span>
                      <span class="w-[2.4em] text-sm text-faint">{weekdayOf(d.date)}</span>
                      <span class="min-w-0 flex-1 overflow-hidden text-ellipsis whitespace-nowrap text-sm text-muted-foreground max-[760px]:hidden">
                        {d.summary?.categories.map((c) => (
                          <span key={c.code} class="mr-3.5">
                            <span class="mr-1.5 text-faint">{c.code}</span>
                            {c.new + c.cross}
                          </span>
                        ))}
                      </span>
                      <Icon name="right" class="ml-auto size-[15px] flex-none text-faint group-hover:text-foreground" />
                    </a>
                  ))}
                </div>
              ))}
            </Card>
            <Pager page={cur} pages={pages} onChange={goPage} />
          </Block>
        </>
      )}
    </Shell>
  )
}
