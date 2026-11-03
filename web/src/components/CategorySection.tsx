// 一个分类：先列新提交，再列 cross-list；篇数跟着范围和搜索走
import type { Scope } from '../lib/store'
import type { CategoryView, PaperView } from '../lib/view'
import { PaperCard } from './PaperCard'

export function CategorySection({
  cat,
  news,
  crosses,
  scope,
  date
}: {
  cat: CategoryView
  news: PaperView[]
  crosses: PaperView[]
  scope: Scope
  date: string
}) {
  const showNew = scope !== 'cross'
  const showCross = scope !== 'primary'
  return (
    <section id={cat.anchor} class="mt-[46px] max-[760px]:mt-9">
      <div class="mb-3.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 class="m-0 text-xl font-semibold">{cat.code}</h2>
        <span class="text-sm text-faint">{cat.name}</span>
        <span class="ml-auto text-sm tabular-nums text-faint">
          {showNew && <span>新提交 {news.length}</span>}
          {showNew && showCross && ' '}
          {showCross && <span class={showNew ? 'ml-3.5' : ''}>cross-list {crosses.length}</span>}
        </span>
      </div>
      {showNew && (
        <div class="flex flex-col gap-3.5">
          {news.map((p) => (
            <PaperCard key={p.id} paper={p} date={date} />
          ))}
        </div>
      )}
      {showCross && cat.cross.length > 0 && (
        <>
          {scope === 'all' && (
            <div id={`${cat.anchor}-cross`} class="mb-3 mt-7 flex items-baseline gap-2.5 text-sm font-semibold text-faint">
              cross-list
              <span class="ml-auto font-normal tabular-nums">{crosses.length}</span>
            </div>
          )}
          <div class="flex flex-col gap-3.5">
            {crosses.map((p) => (
              <PaperCard key={p.id} paper={p} date={date} />
            ))}
          </div>
        </>
      )}
    </section>
  )
}
