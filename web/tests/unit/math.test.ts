import { describe, expect, it } from 'vitest'
import { loadMath, mathReady, renderMath } from '../../src/lib/math'

describe('renderMath', () => {
  it('returns null until KaTeX is loaded', () => {
    expect(mathReady.value).toBe(false)
    expect(renderMath('x', false)).toBeNull()
  })

  it('typesets, caches, and returns null for TeX it cannot typeset', async () => {
    await loadMath()
    expect(mathReady.value).toBe(true)
    const html = renderMath(String.raw`2\times`, false)
    expect(html).toContain('class="katex"')
    expect(renderMath(String.raw`2\times`, false)).toBe(html)
    expect(renderMath(String.raw`\sum_i x_i`, true)).toContain('katex-display')
    expect(renderMath(String.raw`\notacommand{x}`, false)).toBeNull()
  })

  it('reads a lone % as a percent sign, not a comment', () => {
    // 看得见的那一份（katex-html）里的文字
    const shown = (tex: string) => (renderMath(tex, false) ?? '').split('class="katex-html"')[1]?.replace(/^[^>]*>/, '').replace(/<[^>]+>/g, '')
    expect(shown(String.raw`\textbf{92.52%}`)).toBe('92.52%')
    expect(shown(String.raw`4.1\text{%}`)).toBe('4.1%')
    expect(shown(String.raw`50\%`)).toBe('50%')
    // \\ 是换行，后面的 % 也当百分号
    expect(shown(String.raw`a\\%b`)).toBe('a%b')
  })

  it('supports \\unicode and \\mbox like MathJax does', () => {
    expect(renderMath(String.raw`a\unicode{x2014}b`, false)).toContain('—')
    expect(renderMath(String.raw`\mbox{Net}`, false)).toContain('Net')
  })

  it('does not let \\gdef in one formula leak into the next', () => {
    expect(renderMath(String.raw`\gdef\foo{1}\foo`, false)).not.toBeNull()
    expect(renderMath(String.raw`\foo`, false)).toBeNull()
  })

  it('links only http(s) in \\href', () => {
    expect(renderMath(String.raw`\href{https://a.org}{x}`, false)).toContain('href="https://a.org"')
    // TeX 原文会出现在 MathML 的 annotation 里（文字），但不能变成链接
    expect(renderMath(String.raw`\href{javascript:alert(1)}{x}`, false)).not.toMatch(/href="javascript:/)
  })
})
