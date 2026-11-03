// 顶栏：站名、（每日页的）搜索、设置、收藏
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'
import { matchCount, query, saved } from '../lib/store'
import { Icon } from './Icon'
import { Popover } from './Popover'
import { Settings } from './Settings'
import { IconButton } from './ui'
import css from './Header.module.css'

export function Header({ daily, onOpenSaved }: { daily: boolean; onOpenSaved: () => void }) {
  const [floating, setFloating] = useState(false)
  const [searching, setSearching] = useState(false)
  const [setOpen, setSetOpen] = useState(false)
  const setBtn = useRef<HTMLSpanElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const [draft, setDraft] = useState(query.value)

  useEffect(() => {
    let raf = 0
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(() => ((raf = 0), setFloating(window.scrollY > 20)))
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // 按 / 打开搜索
  useEffect(() => {
    if (!daily) return
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName ?? ''
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA') {
        e.preventDefault()
        setSearching(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [daily])

  // 搜索框一出来就拿到焦点（在下一个按键之前），按 / 以后紧接着打的字不会丢
  useLayoutEffect(() => {
    if (searching) input.current?.focus()
  }, [searching])

  // 输入停一下再搜，几百篇卡片不用每个字都重排
  useEffect(() => {
    const t = window.setTimeout(() => (query.value = draft.trim()), 120)
    return () => window.clearTimeout(t)
  }, [draft])

  const closeSearch = () => {
    setSearching(false)
    setDraft('')
  }

  return (
    <header class={`${css.top} ${floating ? css.floating : ''}`}>
      <div class="mx-auto max-w-[824px] px-8 max-[760px]:px-4">
        <div class={css.bar}>
          <a class="whitespace-nowrap text-xl font-bold max-[760px]:text-lg" href="/">
            arXiv Reader
          </a>
          <span class="flex-1" />
          {daily && searching && (
            <label class="flex h-[34px] w-[280px] items-center gap-2 rounded-lg border border-border bg-card px-2.5 max-[760px]:absolute max-[760px]:inset-x-0 max-[760px]:top-[calc(100%+8px)] max-[760px]:w-auto max-[760px]:shadow-[0_10px_30px_hsl(240_10%_4%/.12)]">
              <Icon name="search" class="size-[15px] text-faint" />
              <input
                ref={input}
                type="search"
                placeholder="搜索"
                autocomplete="off"
                spellcheck={false}
                value={draft}
                onInput={(e) => setDraft(e.currentTarget.value)}
                onKeyDown={(e) => e.key === 'Escape' && closeSearch()}
                class="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-faint max-[760px]:text-base [&::-webkit-search-cancel-button]:hidden"
              />
              {query.value && <span class="whitespace-nowrap text-xs tabular-nums text-faint">{matchCount.value} 篇</span>}
            </label>
          )}
          {daily && <IconButton icon="search" label="搜索" active={searching} onClick={() => (searching ? closeSearch() : setSearching(true))} />}
          <span ref={setBtn} class="inline-flex">
            <IconButton icon="sliders" label="设置" active={setOpen} onClick={() => setSetOpen(!setOpen)} />
          </span>
          <IconButton icon="star" label="收藏" onClick={onOpenSaved}>
            {saved.value.length > 0 && (
              <span class="absolute -right-1.5 -top-1.5 h-[17px] min-w-[17px] rounded-full bg-foreground px-1 text-center text-xs font-semibold leading-[17px] text-background">
                {saved.value.length}
              </span>
            )}
          </IconButton>
          <Popover anchor={setBtn} open={setOpen} onClose={() => setSetOpen(false)} label="设置">
            <Settings daily={daily} />
          </Popover>
        </div>
      </div>
    </header>
  )
}
