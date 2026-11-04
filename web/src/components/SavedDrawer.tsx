// 收藏清单：跨日期累积，存在浏览器里；可以复制 ID
import { useEffect } from 'preact/hooks'
import { loadMath } from '../lib/math'
import { clearSaved, removeSaved, saved, toast } from '../lib/store'
import { mayHaveMath } from '../lib/tex'
import { Icon } from './Icon'
import { Rich } from './Rich'
import { Button, IconButton } from './ui'
import css from './Drawer.module.css'

async function copy(text: string): Promise<void> {
  if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text)
  const area = document.createElement('textarea')
  area.value = text
  area.style.position = 'fixed'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.select()
  const ok = document.execCommand('copy')
  document.body.removeChild(area)
  if (!ok) throw new Error('copy failed')
}

export function SavedDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const items = saved.value

  // 首页没有加载 KaTeX；收藏的标题里有公式，打开抽屉时再加载
  useEffect(() => {
    if (open && items.some((x) => mayHaveMath(x.title))) loadMath().catch(() => {})
  }, [open, items])

  useEffect(() => {
    const narrow = window.matchMedia('(max-width: 760px)').matches
    document.documentElement.classList.toggle('lock', open && narrow)
    if (!open) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [open])

  const copyAll = (withTitle: boolean) => {
    if (!items.length) return
    const text = items.map((x) => (withTitle && x.title ? `${x.id}  ${x.title}` : x.id)).join('\n')
    copy(text).then(
      () => toast(`已复制 ${items.length} 篇`),
      () => toast('复制失败')
    )
  }

  return (
    <>
      <div class={`${css.mask} ${open ? css.on : ''}`} onClick={onClose} />
      <aside class={`${css.drawer} ${open ? css.on : ''}`} aria-label="收藏" aria-hidden={!open}>
        <div class="flex items-baseline gap-2.5">
          <h2 class="m-0 text-xl font-semibold">收藏</h2>
          <span class="text-sm tabular-nums text-faint">{items.length}</span>
          <IconButton icon="x" label="关闭" class="ml-auto self-center" onClick={onClose} />
        </div>
        <div class="mt-4 flex flex-wrap gap-2">
          <Button dark class="h-8" onClick={() => copyAll(false)}>
            复制 ID
          </Button>
          <Button class="h-8" onClick={() => copyAll(true)}>
            复制 ID 和标题
          </Button>
          <Button danger class="h-8" onClick={() => items.length && window.confirm(`清空 ${items.length} 篇收藏？`) && clearSaved()}>
            清空
          </Button>
        </div>
        <div class="-mr-1 mt-3.5 min-h-0 flex-1 overflow-y-auto pr-1">
          {[...items].reverse().map((x) => (
            <div key={x.id} class="flex items-start gap-2.5 border-t border-border py-[11px] first:border-t-0">
              <div class="min-w-0 flex-1">
                <a class="line-clamp-2 text-sm hover:underline hover:underline-offset-[3px]" href={`https://arxiv.org/abs/${x.id}`} target="_blank" rel="noopener">
                  {x.title ? <Rich text={x.title} links={false} /> : x.id}
                </a>
                <div class="mt-0.5 font-mono text-xs text-faint">
                  {x.id}
                  {x.date && ` · ${x.date}`}
                </div>
              </div>
              <button type="button" aria-label="移除" class="mt-px rounded-md p-1 text-faint hover:bg-secondary hover:text-foreground" onClick={() => removeSaved(x.id)}>
                <Icon name="x" class="size-3.5" />
              </button>
            </div>
          ))}
        </div>
      </aside>
    </>
  )
}
