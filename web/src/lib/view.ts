import { anchorOf, categoryName } from './categories'
import type { DailyFile, Kind, Paper } from './types'

export interface PaperView {
  id: string
  kind: Kind
  title: string
  titleZh: string
  authors: string
  abstract: string
  abstractZh: string
  comments: string
  primary: string
  arxivUrl: string
  pdfUrl: string
  htmlUrl: string
  hjfyUrl: string
  /** 搜索用：标题、作者、摘要、Comments 拼起来转小写 */
  haystack: string
}

export interface CategoryView {
  code: string
  name: string
  anchor: string
  new: PaperView[]
  cross: PaperView[]
}

// 存下来的中文翻译里，公式的反斜杠常常被吃掉：模型在 JSON 里写 \times、\text、\beta、\rho、\frac、\nabla 不转义反斜杠，
// 正好是 JSON 的 \t \b \r \f \n，解析出来成了控制字符（2026-11-04 时有 3,708 篇）。显示前换回去；只换后面紧跟字母的，
// 真的换行、制表符不动
const LOST: Record<string, string> = { '\t': '\\t', '\b': '\\b', '\f': '\\f', '\r': '\\r', '\n': '\\n' }
export const restoreEscapes = (text: string): string => text.replace(/[\t\b\f\r\n](?=[A-Za-z])/g, (c) => LOST[c])

function toView(p: Paper): PaperView {
  const id = p.arxiv_id
  const view: PaperView = {
    id,
    kind: p.kind === 'cross' ? 'cross' : 'new',
    title: p.title ?? '',
    titleZh: restoreEscapes(p.title_zh ?? ''),
    authors: (p.authors ?? []).join(', '),
    abstract: p.abstract ?? '',
    abstractZh: restoreEscapes(p.abstract_zh ?? ''),
    comments: p.comments ?? '',
    primary: p.primary_category ?? '',
    arxivUrl: p.arxiv_url || `https://arxiv.org/abs/${id}`,
    pdfUrl: p.pdf_url || `https://arxiv.org/pdf/${id}`,
    htmlUrl: `https://arxiv.org/html/${id}`,
    hjfyUrl: p.hjfy_url ?? '',
    haystack: ''
  }
  view.haystack = [id, view.title, view.titleZh, view.authors, view.abstract, view.abstractZh, view.comments]
    .join(' ')
    .toLowerCase()
  return view
}

/** 每个分类拆成新提交和 cross-list 两组，保持列表页上的顺序 */
export function buildDaily(file: DailyFile): CategoryView[] {
  return Object.entries(file.papers_by_category).map(([code, papers]) => {
    const all = papers.map(toView)
    return {
      code,
      name: categoryName(code),
      anchor: anchorOf(code),
      new: all.filter((p) => p.kind === 'new'),
      cross: all.filter((p) => p.kind === 'cross')
    }
  })
}

/** 搜索：空格分开的每个词都要出现 */
export function matches(paper: PaperView, terms: string[]): boolean {
  return terms.every((t) => paper.haystack.includes(t))
}

export const searchTerms = (query: string): string[] => query.toLowerCase().split(/\s+/).filter(Boolean)
