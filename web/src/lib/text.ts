// 摘要和 Comments 的显示：去掉常见的 TeX 写法，把网址变成链接（返回片段，由组件渲染，不拼 HTML）

const TEX_WRAP = /\\(?:emph|textit|textbf|texttt|textsc|mathrm)\{([^{}]*)\}/g
const TEX_ESC = /\\([%&_#$])/g
const TEX_TILDE = /(?<=\S)~(?=\S)/g
const URL_RE = /https?:\/\/[^\s<>"']+/g
const TRAILING = /[.,;:)\]]+$/

export function detex(text: string): string {
  return text.replace(TEX_WRAP, '$1').replace(TEX_ESC, '$1').replace(TEX_TILDE, '\u00a0')
}

export type Segment = { text: string; href?: string }

export function segments(raw: string): Segment[] {
  const text = detex(raw)
  const out: Segment[] = []
  let last = 0
  for (const m of text.matchAll(URL_RE)) {
    let url = m[0]
    const tail = url.match(TRAILING)?.[0] ?? ''
    if (tail) url = url.slice(0, -tail.length)
    const start = m.index ?? 0
    if (start > last) out.push({ text: text.slice(last, start) })
    out.push({ text: url, href: url })
    last = start + url.length
  }
  if (last < text.length) out.push({ text: text.slice(last) })
  return out
}
