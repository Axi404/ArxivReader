import { describe, expect, it } from 'vitest'
import type { DailyFile, Paper } from '../../src/lib/types'
import { buildDaily, matches, restoreEscapes, searchTerms } from '../../src/lib/view'

const paper = (id: string, extra: Partial<Paper> = {}): Paper => ({
  arxiv_id: id,
  title: `Title ${id}`,
  authors: ['Alice', 'Bob'],
  abstract: 'An abstract about diffusion policies.',
  title_zh: '标题',
  abstract_zh: '摘要',
  ...extra
})

describe('buildDaily', () => {
  const file: DailyFile = {
    date: '2026-11-03',
    papers_by_category: {
      'cs.RO': [paper('1', { kind: 'new' }), paper('2', { kind: 'cross', primary_category: 'eess.SY' }), paper('3', { kind: 'new' })],
      'cs.CV': [paper('4')]
    }
  }
  const cats = buildDaily(file)

  it('keeps category order and splits new and cross-list, preserving order', () => {
    expect(cats.map((c) => c.code)).toEqual(['cs.RO', 'cs.CV'])
    expect(cats[0].new.map((p) => p.id)).toEqual(['1', '3'])
    expect(cats[0].cross.map((p) => p.id)).toEqual(['2'])
    expect(cats[0].cross[0].primary).toBe('eess.SY')
  })
  it('treats papers from old files (no kind) as new submissions', () => {
    expect(cats[1].new.map((p) => p.id)).toEqual(['4'])
    expect(cats[1].cross).toEqual([])
  })
  it('fills names, anchors and links', () => {
    expect(cats[0].name).toBe('机器人学')
    expect(cats[0].anchor).toBe('cat-cs-RO')
    expect(cats[0].new[0].pdfUrl).toBe('https://arxiv.org/pdf/1')
    expect(cats[0].new[0].htmlUrl).toBe('https://arxiv.org/html/1')
  })
  it('matches every search term against id, titles, authors and abstracts', () => {
    const p = cats[0].new[0]
    expect(matches(p, searchTerms('  Diffusion   alice '))).toBe(true)
    expect(matches(p, searchTerms('diffusion carol'))).toBe(false)
    expect(matches(p, searchTerms('摘要'))).toBe(true)
    expect(searchTerms('   ')).toEqual([])
  })
})

describe('stored translations', () => {
  it('get back the backslashes JSON parsing turned into control characters', () => {
    // 普通字符串里的 \t \b \r \f \n 正是存下来的样子：制表符、退格……
    expect(restoreEscapes('提升 2$\times$，$\beta$、$\rho$、$\frac{1}{2}$、$\nabla f$')).toBe(String.raw`提升 2$\times$，$\beta$、$\rho$、$\frac{1}{2}$、$\nabla f$`)
  })
  it('keep real line breaks and tabs', () => {
    expect(restoreEscapes('第一段。\n第二段\t。\r\n')).toBe('第一段。\n第二段\t。\r\n')
  })
  it('are repaired in the view, while the English text is left alone', () => {
    const [cat] = buildDaily({
      date: '2026-11-03',
      papers_by_category: { 'cs.RO': [paper('9', { abstract: 'Intro.\nWe propose', abstract_zh: '加速 2$\times$', title_zh: '$\beta$ 标题' })] }
    })
    expect(cat.new[0].abstract).toBe('Intro.\nWe propose')
    expect(cat.new[0].abstractZh).toBe(String.raw`加速 2$\times$`)
    expect(cat.new[0].titleZh).toBe(String.raw`$\beta$ 标题`)
  })
})
