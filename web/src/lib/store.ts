import { effect, signal } from '@preact/signals'

// ---- 设置：主题、摘要怎么显示、范围、首页归档每页几天；存在浏览器里 ----

const MODES = ['auto', 'light', 'dark'] as const
const ABS_MODES = ['both', 'zh', 'en', 'none'] as const
const SCOPES = ['primary', 'cross', 'all'] as const
export const PAGE_SIZES = [10, 20, 50, 100] as const
export type Mode = (typeof MODES)[number]
export type AbsMode = (typeof ABS_MODES)[number]
export type Scope = (typeof SCOPES)[number]
export interface Prefs {
  mode: Mode
  abs: AbsMode
  scope: Scope
  pageSize: number
}

const PREFS_KEY = 'arxiv_reader_prefs_v2'
const DEFAULT_PREFS: Prefs = { mode: 'auto', abs: 'both', scope: 'primary', pageSize: 20 }
const pick = <T>(value: unknown, allowed: readonly T[], fallback: T): T => (allowed.includes(value as T) ? (value as T) : fallback)

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}
function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* 浏览器存储不可用时就不存 */
  }
}

// 构建时会先在没有浏览器的环境里渲染一遍，所以这里先用默认值，打开页面以后由 initStores() 读出存下来的
export const prefs = signal<Prefs>({ ...DEFAULT_PREFS })

export function setPref<K extends keyof Prefs>(key: K, value: Prefs[K]): void {
  prefs.value = { ...prefs.value, [key]: value }
  write(PREFS_KEY, prefs.value)
}

/** 主题：html 上的 dark 类（和博客一样）；自动时跟随系统 */
export function applyTheme(): () => void {
  const media = window.matchMedia('(prefers-color-scheme: dark)')
  const apply = () => {
    const mode = prefs.value.mode
    const dark = mode === 'dark' || (mode === 'auto' && media.matches)
    document.documentElement.classList.toggle('dark', dark)
  }
  media.addEventListener('change', apply)
  const stop = effect(apply)
  return () => {
    stop()
    media.removeEventListener('change', apply)
  }
}

// ---- 收藏：跨日期，存在浏览器里；和旧版页面用同一个 key ----

export interface SavedPaper {
  id: string
  title: string
  date: string
  category: string
  added_at: string
}

const CART_KEY = 'arxiv_reader_paper_cart_v1'

export function normalizeSaved(items: unknown): SavedPaper[] {
  if (!Array.isArray(items)) return []
  const seen = new Set<string>()
  const out: SavedPaper[] = []
  for (const raw of items) {
    if (!raw || typeof raw !== 'object') continue
    const x = raw as Record<string, unknown>
    const id = typeof x.id === 'string' ? x.id.trim() : ''
    if (!id || seen.has(id)) continue
    seen.add(id)
    const str = (k: string) => (typeof x[k] === 'string' ? (x[k] as string) : '')
    out.push({ id, title: str('title'), date: str('date'), category: str('category'), added_at: str('added_at') })
  }
  return out
}

export const saved = signal<SavedPaper[]>([])

/** 存下来的设置读进来了没有（读之前 prefs 是默认值） */
export const prefsReady = signal(false)

/** 页面打开以后读一次浏览器里存的设置和收藏；存的值不认识就用默认的 */
export function initStores(): void {
  const raw = read<Record<string, unknown>>(PREFS_KEY, {}) ?? {}
  prefs.value = {
    mode: pick(raw.mode, MODES, DEFAULT_PREFS.mode),
    abs: pick(raw.abs, ABS_MODES, DEFAULT_PREFS.abs),
    scope: pick(raw.scope, SCOPES, DEFAULT_PREFS.scope),
    pageSize: pick(raw.pageSize, PAGE_SIZES, DEFAULT_PREFS.pageSize)
  }
  saved.value = normalizeSaved(read<unknown>(CART_KEY, []))
  prefsReady.value = true
}

function setSaved(next: SavedPaper[]): void {
  saved.value = next
  write(CART_KEY, next)
}

export const isSaved = (id: string): boolean => saved.value.some((x) => x.id === id)

export function toggleSaved(item: { id: string; title: string; date: string }): void {
  if (isSaved(item.id)) setSaved(saved.value.filter((x) => x.id !== item.id))
  else setSaved([...saved.value, { ...item, category: '', added_at: new Date().toISOString() }])
}

export const removeSaved = (id: string): void => setSaved(saved.value.filter((x) => x.id !== id))
export const clearSaved = (): void => setSaved([])

/** 别的标签页改了收藏，这里跟着变 */
export function syncSavedAcrossTabs(): () => void {
  const onStorage = (e: StorageEvent) => {
    if (e.key === CART_KEY) saved.value = normalizeSaved(read<unknown>(CART_KEY, []))
  }
  window.addEventListener('storage', onStorage)
  return () => window.removeEventListener('storage', onStorage)
}

// ---- 搜索、提示 ----

export const query = signal('')
/** 当前范围里搜到几篇（每日页算好放在这里，顶栏的搜索框里显示） */
export const matchCount = signal(0)

export const toastText = signal('')
let toastTimer = 0
export function toast(text: string): void {
  toastText.value = text
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => (toastText.value = ''), 1600)
}
