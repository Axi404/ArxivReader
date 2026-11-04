// 公式用 KaTeX 排。KaTeX 的脚本只在用得到时加载：每日页和当天的数据一起取，首页的收藏抽屉里有公式时再取。
// 样式在 layouts/Base.astro 里随页面加载（Astro 会把动态导入的 CSS 也放进页面，不如直接写明），字体用到才下载。
// 排不了的（作者自己定义的命令之类）返回 null，由 Rich 显示原文：arXiv 的 MathJax 碰到这种也是显示原文。
import { signal } from '@preact/signals'
import type { KatexOptions } from 'katex'

type Katex = (typeof import('katex'))['default']

let katex: Katex | null = null
let loading: Promise<void> | null = null

/** KaTeX 加载好了没有；组件渲染时读它，加载好以后自动重画 */
export const mathReady = signal(false)

export function loadMath(): Promise<void> {
  loading ??= Promise.all([
    import('katex'),
    // 选中带公式的文字复制时，复制出来的是 LaTeX 原文
    typeof document === 'undefined' ? null : import('katex/contrib/copy-tex')
  ]).then(
    async ([m]) => {
      katex = m.default
      // 几乎每个公式都用的两种字体先下好：卡片出来以后公式不会因为换字体再变宽变窄、把行挤动
      if (typeof document !== 'undefined' && document.fonts)
        await Promise.all(['1em KaTeX_Main', 'italic 1em KaTeX_Math'].map((font) => document.fonts.load(font).catch(() => [])))
      mathReady.value = true
    },
    (err) => {
      loading = null
      throw err
    }
  )
  return loading
}

const OPTIONS: KatexOptions = {
  throwOnError: true,
  strict: 'ignore',
  // \href、\url 只放 http(s) 的链接
  trust: (c) => (c.command === '\\href' || c.command === '\\url') && (c.protocol === 'http' || c.protocol === 'https'),
  maxSize: 10,
  maxExpand: 1000,
  errorColor: 'currentColor'
}

// MathJax 有、KaTeX 没有的：\unicode{x2014}（arXiv 上有人用来打破折号）换成那个字
const UNICODE = /\\unicode\s*\{\s*(?:x([0-9a-fA-F]{1,6})|(\d{1,7}))\s*\}/g
const SPECIAL = /[\\{}$%#&_^~]/
// 没转义的 %：在 TeX 里是注释，会把后半个公式吃掉（$\textbf{92.52%}$）；摘要只有一行，不会真是注释
const PERCENT = /(?<!\\)((?:\\\\)*)%/g
function prepare(tex: string): string {
  return tex
    .replace(UNICODE, (all, hex?: string, dec?: string) => {
      const cp = hex ? parseInt(hex, 16) : Number(dec)
      const ch = cp > 0 && cp <= 0x10ffff ? String.fromCodePoint(cp) : ''
      return ch && !SPECIAL.test(ch) ? `\\text{${ch}}` : all
    })
    .replace(PERCENT, '$1\\%')
}

/** 用给定的 KaTeX 排一个公式；排不了就抛出错误（分开写是为了能拿整个数据集来测） */
export function typeset(k: Katex, tex: string, display: boolean): string {
  // macros 每次给一份新的：KaTeX 碰到 \gdef 会往里写，不能让一篇摘要的定义带到别的摘要里
  return k.renderToString(prepare(tex), { ...OPTIONS, displayMode: display, macros: { '\\mbox': '\\text{#1}' } })
}

const cache = new Map<string, string | null>()

/** 排好的 HTML（KaTeX 自己转义过，可以直接放进页面）；还没加载或者排不了返回 null */
export function renderMath(tex: string, display: boolean): string | null {
  if (!katex) return null
  const key = (display ? 'D' : 'I') + tex
  let html = cache.get(key)
  if (html === undefined) {
    try {
      html = typeset(katex, tex, display)
    } catch {
      html = null
    }
    cache.set(key, html)
  }
  return html
}
