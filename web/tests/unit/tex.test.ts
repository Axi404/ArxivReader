import { describe, expect, it } from 'vitest'
import { mayHaveMath, parseTex, type TexNode } from '../../src/lib/tex'

// 节点写成短字符串好对照：行内公式 ⟪…⟫，单独一行 ⟪⟪…⟫⟫，链接 [文字](网址)，样式 <b>…</b>
const flat = (nodes: TexNode[]): string =>
  nodes
    .map((n) =>
      n.kind === 'text'
        ? n.text
        : n.kind === 'math'
          ? n.display
            ? `⟪⟪${n.tex}⟫⟫`
            : `⟪${n.tex}⟫`
          : n.kind === 'link'
            ? `[${flat(n.children)}](${n.href})`
            : `<${n.style}>${flat(n.children)}</${n.style}>`
    )
    .join('')
const p = (s: string) => flat(parseTex(s))

describe("formulas, paired the way arXiv's MathJax pairs them", () => {
  it('finds inline and display formulas', () => {
    expect(p(String.raw`a 2$\times$ speedup`)).toBe(String.raw`a 2⟪\times⟫ speedup`)
    expect(p(String.raw`$$\sum_i x_i$$ and \[y\] and \(z\)`)).toBe(String.raw`⟪⟪\sum_i x_i⟫⟫ and ⟪⟪y⟫⟫ and ⟪z⟫`)
  })
  it('keeps the source for showing when KaTeX cannot typeset it', () => {
    expect(parseTex('x $a^2$ y')[1]).toEqual({ kind: 'math', tex: 'a^2', display: false, source: '$a^2$' })
  })
  it('treats \\$ as a dollar sign, also inside formulas', () => {
    expect(p(String.raw`costs \$5 and $x$`)).toBe('costs $5 and ⟪x⟫')
    expect(p(String.raw`$a \$ b$`)).toBe(String.raw`⟪a \$ b⟫`)
  })
  it('closes where braces balance, or else at the first closer', () => {
    expect(p('${a$b}$ c')).toBe('⟪{a$b}⟫ c')
    expect(p('$a{b$ c')).toBe('⟪a{b⟫ c')
  })
  it('leaves openers without a closer as text and keeps pairing after them', () => {
    expect(p('only $ one')).toBe('only $ one')
    expect(p('$$x$ y')).toBe('$$x$ y')
    expect(p('pay $5 and $10 now')).toBe('pay ⟪5 and ⟫10 now')
  })
  it('knows when a text may contain formulas', () => {
    expect(mayHaveMath('a $x$')).toBe(true)
    expect(mayHaveMath(String.raw`a \(x\)`)).toBe(true)
    expect(mayHaveMath(String.raw`plain \textbf{text}`)).toBe(false)
  })
})

describe('LaTeX outside formulas', () => {
  it('styles text commands, also when a formula is inside', () => {
    expect(p(String.raw`\textbf{Fast$\pi_0$} and \emph{a} \textit{b} \texttt{c} \textsc{d} \underline{e} X\textsuperscript{2}`)).toBe(
      String.raw`<b>Fast⟪\pi_0⟫</b> and <i>a</i> <i>b</i> <tt>c</tt> <sc>d</sc> <u>e</u> X<sup>2</sup>`
    )
  })
  it('applies {\\bf …} switches to the end of their group', () => {
    expect(p(String.raw`a {\bf b c} d \textbf{\em e}`)).toBe('a <b>b c</b> d <b><i>e</i></b>')
  })
  it('drops plain braces and keeps the content of \\text, \\mbox, \\textcolor', () => {
    expect(p(String.raw`{CAMO} \mbox{x} \textcolor{purple}{here}`)).toBe('CAMO x here')
  })
  it('turns \\href, \\url and bare URLs into links', () => {
    expect(p(String.raw`see \href{https://a.org/x\_y}{\texttt{code}} or \url{https://b.org/~u}.`)).toBe(
      'see [<tt>code</tt>](https://a.org/x_y) or [https://b.org/~u](https://b.org/~u).'
    )
    expect(p('Code: https://github.com/a/b. More (see https://en.wikipedia.org/wiki/A_(b)).')).toBe(
      'Code: [https://github.com/a/b](https://github.com/a/b). More (see [https://en.wikipedia.org/wiki/A_(b)](https://en.wikipedia.org/wiki/A_(b))).'
    )
    expect(p(String.raw`\href{mailto:a@b.org}{mail}`)).toBe('mail')
  })
  it('ends bare URLs where Chinese text starts and keeps ~ inside them', () => {
    expect(p('代码见 https://x.org/~a/b。我们')).toBe('代码见 [https://x.org/~a/b](https://x.org/~a/b)。我们')
  })
  it('converts accents and special letters', () => {
    expect(p(String.raw`Poincar\'e, G\"{o}del, Fran\c{c}ois, \'{\i}, Erd\H{o}s, \ss, \o, \L{}\'od\'z`)).toBe('Poincaré, Gödel, François, í, Erdős, ß, ø, Łódź')
  })
  it('converts quotes, dashes, ties, escapes and degrees', () => {
    expect(p(String.raw`10--20 a---b Fig.~3 ~70% (~5) 50\% \& 360{\deg}`)).toBe('10–20 a—b Fig.\u00a03 ~70% (~5) 50% & 360°')
    expect(p("``quoted''")).toBe('“quoted”')
  })
  it('shows unknown commands with their braces, and still processes what is inside, like arXiv', () => {
    expect(p(String.raw`our \method{} beats \cite{x} and \SI{10}{\meter}, \textbf alone`)).toBe(
      String.raw`our \method{} beats \cite{x} and \SI{10}{\meter}, \textbf alone`
    )
    expect(p(String.raw`better \modification{($p < 0.001$)}, \redclaim{\textbf{x}`)).toBe(String.raw`better \modification{(⟪p < 0.001⟫)}, \redclaim{<b>x</b>`)
  })
  it('keeps stray closing braces and lone backslashes', () => {
    expect(p('a } b \\')).toBe('a } b \\')
  })
  it('passes plain text through unchanged', () => {
    const plain = 'We train 3 policies on 1,200 demos (95% CI) & evaluate them: 12.5x faster? Yes. 中文也一样。'
    expect(p(plain)).toBe(plain)
  })
})
