// 目录：每一项是页面上的一块；跟着滚动标出看到的那一项，左边一道短竖线滑过去
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'

export interface TocItem {
  id: string
  label: string
  count: number
  sub?: boolean
}

const LINE = 110 // 顶栏下面那条线：一块的顶边过了这条线，就算看到它了
const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function Toc({ items }: { items: TocItem[] }) {
  const [cur, setCur] = useState(0)
  const [ind, setInd] = useState<{ y: number; h: number } | null>(null)
  const list = useRef<HTMLDivElement>(null)
  const locked = useRef(false)
  // 点过的那一项：页面滚不到它（最后几块很短）时也一直标着它，离开落点 40px 才放开
  const pinned = useRef<{ index: number; y: number } | null>(null)
  // 第几次点击：滚动途中又点了别的项，前一次的收尾就不算数了
  const jumpId = useRef(0)

  useEffect(() => {
    let raf = 0
    const spy = () => {
      raf = 0
      if (locked.current || !items.length) return
      const pin = pinned.current
      if (pin && Math.abs(window.scrollY - pin.y) < 40) return setCur(pin.index)
      pinned.current = null
      let k = 0
      items.forEach((item, n) => {
        const el = document.getElementById(item.id)
        if (el && el.getBoundingClientRect().top <= LINE) k = n
      })
      if (window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 4) k = items.length - 1
      setCur(k)
    }
    const onScroll = () => {
      if (!raf) raf = requestAnimationFrame(spy)
    }
    pinned.current = null
    spy()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [items])

  useLayoutEffect(() => {
    const a = list.current?.querySelectorAll<HTMLAnchorElement>('a')[cur]
    setInd(a ? { y: a.offsetTop, h: a.offsetHeight } : null)
  }, [cur, items])

  const jump = (e: MouseEvent, k: number) => {
    e.preventDefault()
    const el = document.getElementById(items[k].id)
    if (!el) return
    const id = ++jumpId.current
    setCur(k)
    locked.current = true
    pinned.current = null
    const smooth = !reduced()
    let timer = 0
    const done = () => {
      window.removeEventListener('scrollend', done)
      window.clearTimeout(timer)
      if (id !== jumpId.current) return
      locked.current = false
      pinned.current = { index: k, y: window.scrollY }
    }
    window.addEventListener('scrollend', done)
    timer = window.setTimeout(done, smooth ? 1500 : 50)
    el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' })
    history.replaceState(null, '', `#${items[k].id}`)
  }

  return (
    <nav aria-label="目录" class="sticky top-[110px] mt-[30px] max-h-[calc(100vh-150px)] overflow-y-auto [scrollbar-width:none]">
      <div ref={list} class="relative flex flex-col border-l border-border pl-3.5">
        {ind && (
          <span
            class="absolute -left-px top-0 w-0.5 rounded-sm bg-foreground transition-[transform,height] duration-300 ease-[cubic-bezier(.22,1,.36,1)]"
            style={{ transform: `translateY(${ind.y}px)`, height: `${ind.h}px` }}
          />
        )}
        {items.map((item, k) => (
          <a
            key={item.id}
            href={`#${item.id}`}
            aria-current={k === cur ? 'location' : undefined}
            onClick={(e) => jump(e, k)}
            class={`flex gap-2 py-1 text-sm leading-5 transition-colors ${item.sub ? 'pl-3.5' : ''} ${
              k === cur ? 'font-semibold text-foreground' : 'text-faint hover:text-foreground'
            }`}
          >
            <span>{item.label}</span>
            <span class="ml-auto tabular-nums">{item.count}</span>
          </a>
        ))}
      </div>
    </nav>
  )
}
