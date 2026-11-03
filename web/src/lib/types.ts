// 后端 JSON 的形状（见 src/arxiv_reader/storage.py 和 web_server.py）

export type Kind = 'new' | 'cross'

export interface Paper {
  arxiv_id: string
  title: string
  authors?: string[]
  abstract?: string
  title_zh?: string | null
  abstract_zh?: string | null
  comments?: string | null
  primary_category?: string | null
  arxiv_url?: string
  pdf_url?: string
  hjfy_url?: string | null
  /** 这篇在当前分类里是新提交还是 cross-list；2026-11 以前的文件没有这个字段，都是新提交 */
  kind?: Kind
}

export interface DailyFile {
  date: string
  format?: number
  papers_by_category: Record<string, Paper[]>
}

export interface CategorySummary {
  code: string
  new: number
  cross: number
  translated: number
}

export interface DaySummary {
  total: number
  new: number
  cross: number
  translated: number
  categories: CategorySummary[]
}

export interface Overview {
  days: { date: string; summary: DaySummary | null }[]
  stats: { days: number; papers: number }
  traffic: { daily: number; total: number }
}
