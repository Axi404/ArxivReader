// 贴着按钮弹出来的小框：点按钮开关，点外面或按 Esc 收起
import type { ComponentChildren, RefObject } from 'preact'
import { useEffect, useLayoutEffect, useRef, useState } from 'preact/hooks'

export function Popover({
  anchor,
  open,
  onClose,
  align = 'right',
  class: cls = '',
  children
}: {
  anchor: RefObject<HTMLElement | null>
  open: boolean
  onClose: () => void
  align?: 'left' | 'right'
  class?: string
  children: ComponentChildren
}) {
  const box = useRef<HTMLDivElement>(null)
  const [pos, setPos] = useState({ top: 0, left: 0 })

  useLayoutEffect(() => {
    if (!open) return
    const place = () => {
      const a = anchor.current?.getBoundingClientRect()
      const w = box.current?.offsetWidth ?? 0
      if (!a) return
      const left = align === 'left' ? a.left : a.right - w
      setPos({ top: Math.round(a.bottom + 10), left: Math.max(12, Math.min(Math.round(left), window.innerWidth - w - 12)) })
    }
    place()
    window.addEventListener('resize', place)
    window.addEventListener('scroll', place, { passive: true })
    return () => {
      window.removeEventListener('resize', place)
      window.removeEventListener('scroll', place)
    }
  }, [open, align])

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!box.current?.contains(t) && !anchor.current?.contains(t)) onClose()
    }
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  if (!open) return null
  return (
    <div
      ref={box}
      role="dialog"
      class={`fixed z-50 animate-[pop-in_.16s_ease_both] rounded-xl border border-border bg-card shadow-[0_10px_30px_hsl(240_10%_4%/.14)] ${cls}`}
      style={{ top: `${pos.top}px`, left: `${pos.left}px` }}
    >
      {children}
    </div>
  )
}
