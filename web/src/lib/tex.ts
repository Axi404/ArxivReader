// 摘要、标题、Comments 里的 LaTeX：解析成节点，交给 Rich 组件渲染（不拼 HTML）。
//
// 公式的找法照 arXiv 列表页上的 MathJax 2.7（tex2jax；inlineMath 只有 $…$，processEscapes 打开）：
// $…$ 是行内公式，$$…$$、\[…\] 单独一行，另外也认 \(…\)；\$ 是美元符号；结束符要在花括号配平的地方才算，
// 到最后都配不平就用遇到的第一个；找不到结束符的开始符当普通文字。这样哪些 $ 配成一对和 arXiv 上一样。
//
// 公式外面：\textbf、\emph、\textsc 这类排成对应的样子（{\bf …} 这样的开关也认）；\href、\url 和裸网址变成链接；
// 重音（\'e、\"o、\c{c}）、``…''、--、---、~、\% 这类换成对应的字符；不认识的命令连同紧跟的参数原样显示，和 arXiv 上一样。

export type Style = 'b' | 'i' | 'tt' | 'sc' | 'u' | 'sup' | 'sub'
export type TexNode =
  | { kind: 'text'; text: string }
  | { kind: 'math'; tex: string; display: boolean; source: string }
  | { kind: 'link'; href: string; children: TexNode[] }
  | { kind: 'style'; style: Style; children: TexNode[] }

const STYLES: Record<string, Style> = {
  textbf: 'b',
  emph: 'i',
  textit: 'i',
  textsl: 'i',
  texttt: 'tt',
  textsc: 'sc',
  underline: 'u',
  uline: 'u',
  textsuperscript: 'sup',
  textsubscript: 'sub'
}
// {\bf …} 这样的开关：管到所在的这一组结束
const SWITCHES: Record<string, Style> = { bf: 'b', bfseries: 'b', em: 'i', it: 'i', itshape: 'i', sl: 'i', tt: 'tt', ttfamily: 'tt', sc: 'sc', scshape: 'sc' }
// 只留内容
const PLAIN = new Set(['text', 'textrm', 'textsf', 'textnormal', 'textup', 'textmd', 'mbox', 'hbox'])
const SYMBOLS: Record<string, string> = {
  ss: 'ß',
  ae: 'æ',
  AE: 'Æ',
  oe: 'œ',
  OE: 'Œ',
  aa: 'å',
  AA: 'Å',
  o: 'ø',
  O: 'Ø',
  l: 'ł',
  L: 'Ł',
  i: 'ı',
  j: 'ȷ',
  ldots: '…',
  dots: '…',
  textellipsis: '…',
  textendash: '–',
  textemdash: '—',
  textquoteleft: '‘',
  textquoteright: '’',
  textquotedblleft: '“',
  textquotedblright: '”',
  textasciitilde: '~',
  textasciicircum: '^',
  textbackslash: '\\',
  textbullet: '•',
  textdegree: '°',
  // 公式外面的 \deg 都是当度数符号用的（360{\deg}、1.23{\deg}）
  deg: '°',
  degree: '°',
  S: '§',
  P: '¶',
  dag: '†',
  ddag: '‡',
  copyright: '©',
  textregistered: '®',
  texttrademark: '™',
  LaTeX: 'LaTeX',
  TeX: 'TeX'
}
// \% 这类：反斜杠后面跟一个符号
const ESCAPES: Record<string, string> = {
  '%': '%',
  '&': '&',
  _: '_',
  '#': '#',
  $: '$',
  '{': '{',
  '}': '}',
  '\\': ' ',
  ' ': ' ',
  '\n': ' ',
  ',': '\u2009',
  ';': ' ',
  ':': ' ',
  '!': '',
  '-': '',
  '/': '',
  '@': ''
}
// 重音：前七个是 \'e 这样的符号命令，后面是 \c{c} 这样的字母命令
const ACCENTS: Record<string, string> = {
  "'": '\u0301',
  '`': '\u0300',
  '^': '\u0302',
  '"': '\u0308',
  '~': '\u0303',
  '=': '\u0304',
  '.': '\u0307',
  c: '\u0327',
  v: '\u030c',
  u: '\u0306',
  H: '\u030b',
  k: '\u0328',
  r: '\u030a'
}
// 粘连（y）的正则：从 lastIndex 处匹配，不用切字符串
const ACCENT_ARG = /\s*(?:\{\s*(\\[ij](?![A-Za-z])|[A-Za-z]?)\s*\}|(\\[ij](?![A-Za-z])|[A-Za-z]))/y
const URL = /https?:\/\/[A-Za-z0-9\-._~:/?#@!$&()*+,;=%]+/y
const NAME = /[A-Za-z]+/y
const BRACE = /\s*\{/y
const typography = (s: string): string => s.replace(/---/g, '—').replace(/--/g, '–').replace(/``/g, '“').replace(/''/g, '”')
const count = (s: string, c: string): number => s.split(c).length - 1

/** 从 from 往后找公式的结束符 close：花括号配平时的那个；一直配不平就用第一个；没有返回 -1 */
function findClose(src: string, from: number, close: string): number {
  let braces = 0
  let first = -1
  for (let i = from; i < src.length; i++) {
    if (src.startsWith(close, i)) {
      if (braces === 0) return i
      if (first < 0) first = i
      i += close.length - 1
    } else if (src[i] === '\\') i++
    else if (src[i] === '{') braces++
    else if (src[i] === '}' && braces > 0) braces--
  }
  return first
}

export function parseTex(src: string): TexNode[] {
  let i = 0
  // 刚结束的那一组是不是读到了右括号（还是一直到了结尾）
  let groupClosed = false
  const at = (re: RegExp): RegExpExecArray | null => {
    re.lastIndex = i
    return re.exec(src)
  }

  // 一个花括号参数（前面可以有空格）：解析里面的内容，i 移到右括号后面；不是左括号就返回 null
  const arg = (): TexNode[] | null => {
    const m = at(BRACE)
    if (!m) return null
    i += m[0].length
    return seq(true)
  }

  // 一个花括号参数的原文（网址用），括号要配平
  const rawArg = (): string | null => {
    const m = at(BRACE)
    if (!m) return null
    let depth = 1
    for (let k = i + m[0].length; k < src.length; k++) {
      if (src[k] === '\\') k++
      else if (src[k] === '{') depth++
      else if (src[k] === '}' && --depth === 0) {
        const raw = src.slice(i + m[0].length, k)
        i = k + 1
        return raw
      }
    }
    return null
  }

  // 重音的参数：{x}、一个字母，或者 \i \j；读不到返回 null，i 不动
  const accent = (mark: string): string | null => {
    const m = at(ACCENT_ARG)
    if (!m) return null
    i += m[0].length
    const base = (m[1] ?? m[2] ?? '').replace('\\', '')
    if (!base) return mark === ACCENTS['~'] ? '~' : mark === ACCENTS['^'] ? '^' : ''
    return (base + mark).normalize('NFC')
  }

  // 从 i 开始的公式（开始符 open，结束符 close）；没有结束符返回 null，i 不动
  const math = (open: string, close: string, display: boolean): TexNode | null => {
    const from = i + open.length
    const end = findClose(src, from, close)
    if (end < 0) return null
    const stop = end + close.length
    const node: TexNode = { kind: 'math', tex: src.slice(from, end), display, source: src.slice(i, stop) }
    i = stop
    return node
  }

  // 裸网址：去掉句末的标点；右括号只在比左括号多的时候去掉
  const bareUrl = (): TexNode | null => {
    const m = at(URL)
    if (!m) return null
    let url = m[0]
    for (;;) {
      const last = url[url.length - 1]
      if ('.,;:!?'.includes(last) || (last === ')' && count(url, ')') > count(url, '('))) url = url.slice(0, -1)
      else break
    }
    if (/^https?:\/\/$/.test(url)) return null
    i += url.length
    return { kind: 'link', href: url, children: [{ kind: 'text', text: url }] }
  }

  // 一串内容，到右括号（inGroup 时，右括号也读掉）或者结尾为止
  const seq = (inGroup: boolean): TexNode[] => {
    const nodes: TexNode[] = []
    let buf = ''
    const flush = () => {
      if (buf) nodes.push({ kind: 'text', text: typography(buf) })
      buf = ''
    }
    const push = (...items: TexNode[]) => {
      flush()
      nodes.push(...items)
    }

    let closed = false
    while (i < src.length) {
      const c = src[i]
      if (c === '}') {
        i++
        if (inGroup) {
          closed = true
          break
        }
        buf += '}'
        continue
      }
      if (c === '{') {
        i++
        push(...seq(true))
        continue
      }
      if (c === '$') {
        const display = src[i + 1] === '$'
        const node = display ? math('$$', '$$', true) : math('$', '$', false)
        if (node) push(node)
        else {
          buf += display ? '$$' : '$'
          i += display ? 2 : 1
        }
        continue
      }
      if (c === '~') {
        // ~ 是不断行的空格；前面是空白或左括号的是“大约”（~70%、(~$25），照原样
        buf += /[\s([]/.test(src[i - 1] ?? ' ') || /\s/.test(src[i + 1] ?? ' ') ? '~' : '\u00a0'
        i++
        continue
      }
      if (c === 'h' && (src.startsWith('https://', i) || src.startsWith('http://', i))) {
        const node = bareUrl()
        if (node) {
          push(node)
          continue
        }
      }
      if (c !== '\\') {
        buf += c
        i++
        continue
      }

      // ---- 反斜杠 ----
      const start = i
      const next = src[i + 1] ?? ''
      if (next === '(' || next === '[') {
        const node = next === '[' ? math('\\[', '\\]', true) : math('\\(', '\\)', false)
        if (node) push(node)
        else {
          buf += src.slice(i, i + 2)
          i += 2
        }
        continue
      }
      if (next in ESCAPES) {
        buf += ESCAPES[next]
        i += 2
        continue
      }
      if (next in ACCENTS && !/[A-Za-z]/.test(next)) {
        i += 2
        const ch = accent(ACCENTS[next])
        buf += ch ?? src.slice(start, i)
        continue
      }
      i++
      const name = at(NAME)?.[0]
      i--
      if (!name) {
        buf += c
        i++
        continue
      }
      i += 1 + name.length
      if (name in STYLES) {
        const children = arg()
        if (children) {
          push({ kind: 'style', style: STYLES[name], children })
          continue
        }
      } else if (name in SWITCHES) {
        while (src[i] === ' ') i++
        flush()
        nodes.push({ kind: 'style', style: SWITCHES[name], children: seq(inGroup) })
        return nodes
      } else if (PLAIN.has(name)) {
        const children = arg()
        if (children) {
          push(...children)
          continue
        }
      } else if (name === 'href') {
        const url = rawArg()
        if (url !== null) {
          const href = url.trim().replace(/\\([%#_&~$])/g, '$1')
          const children = arg() ?? [{ kind: 'text', text: href }]
          if (/^https?:\/\/\S+$/.test(href)) push({ kind: 'link', href, children })
          else push(...children)
          continue
        }
      } else if (name === 'url') {
        const url = rawArg()
        if (url !== null) {
          const href = url.trim().replace(/\\([%#_&~$])/g, '$1')
          push(/^https?:\/\/\S+$/.test(href) ? { kind: 'link', href, children: [{ kind: 'text', text: href }] } : { kind: 'text', text: href })
          continue
        }
      } else if (name === 'textcolor') {
        const color = rawArg()
        const children = color === null ? null : arg()
        if (children) {
          push(...children)
          continue
        }
      } else if (name in ACCENTS) {
        const ch = accent(ACCENTS[name])
        if (ch !== null) {
          buf += ch
          continue
        }
      } else if (name in SYMBOLS) {
        buf += SYMBOLS[name]
        if (src.startsWith('{}', i)) i += 2
        continue
      }
      // 不认识的命令（作者自己定义的 \method 之类），或者参数不对：命令原样显示，紧跟的 {…} 连同括号显示，
      // 括号里照常处理（\modification{($p<0.001$)} 里的公式照排），和 arXiv 上一样
      i = start + 1 + name.length
      buf += src.slice(start, i)
      while (src[i] === '{') {
        i++
        buf += '{'
        const inner = seq(true)
        const ended = groupClosed
        push(...inner)
        if (ended) buf += '}'
      }
    }
    flush()
    groupClosed = closed
    return nodes
  }

  return seq(false)
}

/** 有没有可能含公式（不用逐字扫描的快速判断） */
export const mayHaveMath = (text: string): boolean => /\$|\\[([]/.test(text)
