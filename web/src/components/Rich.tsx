// 一段带 LaTeX 的文字：公式用 KaTeX 排（还没加载好、或者排不了的，显示原文），\textbf 这类排成对应的样子，网址是链接。
// 标题本身在链接里，links={false} 时里面的链接只显示文字
import type { ComponentChildren } from 'preact'
import { useMemo } from 'preact/hooks'
import { mathReady, renderMath } from '../lib/math'
import { parseTex, type TexNode } from '../lib/tex'

const LINK = 'underline decoration-foreground/30 underline-offset-[3px] [overflow-wrap:anywhere] hover:decoration-current'

function show(nodes: TexNode[], links: boolean, ready: boolean): ComponentChildren {
  return nodes.map((n, k) => {
    if (n.kind === 'text') return n.text
    if (n.kind === 'math') {
      const html = ready ? renderMath(n.tex, n.display) : null
      return html === null ? n.source : <span key={k} class="math" dangerouslySetInnerHTML={{ __html: html }} />
    }
    const inner = show(n.children, false, ready)
    if (n.kind === 'link')
      return links ? (
        <a key={k} href={n.href} target="_blank" rel="noopener" class={LINK}>
          {inner}
        </a>
      ) : (
        inner
      )
    switch (n.style) {
      case 'b':
        return <b key={k}>{show(n.children, links, ready)}</b>
      case 'i':
        return <i key={k}>{show(n.children, links, ready)}</i>
      case 'tt':
        return (
          <code key={k} class="font-mono text-[0.92em]">
            {show(n.children, links, ready)}
          </code>
        )
      case 'sc':
        return (
          <span key={k} class="[font-variant:small-caps]">
            {show(n.children, links, ready)}
          </span>
        )
      case 'u':
        return (
          <u key={k} class="underline-offset-[3px]">
            {show(n.children, links, ready)}
          </u>
        )
      case 'sup':
        return <sup key={k}>{show(n.children, links, ready)}</sup>
      case 'sub':
        return <sub key={k}>{show(n.children, links, ready)}</sub>
    }
  })
}

export function Rich({ text, links = true }: { text: string; links?: boolean }) {
  const ready = mathReady.value
  const nodes = useMemo(() => parseTex(text), [text])
  return <>{show(nodes, links, ready)}</>
}
