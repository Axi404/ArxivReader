import { describe, expect, it } from 'vitest'
import { normalizeSaved } from '../../src/lib/store'

describe('normalizeSaved', () => {
  it('keeps valid entries once, in order, and fills missing fields', () => {
    expect(
      normalizeSaved([{ id: ' 2611.1 ', title: 'A' }, { id: '2611.1', title: 'dup' }, null, 'x', { id: '' }, { id: '2611.2', date: '2026-11-03', title: 3 }])
    ).toEqual([
      { id: '2611.1', title: 'A', date: '', category: '', added_at: '' },
      { id: '2611.2', title: '', date: '2026-11-03', category: '', added_at: '' }
    ])
  })
  it('ignores anything that is not a list', () => {
    expect(normalizeSaved({ id: 'x' })).toEqual([])
    expect(normalizeSaved(null)).toEqual([])
  })
})

describe('initStores', () => {
  it('reads stored settings and replaces values it does not know', async () => {
    const data: Record<string, string> = {
      arxiv_reader_prefs_v2: JSON.stringify({ mode: 'dark', scope: 'bogus', pageSize: 50, abs: 'zh' }),
      arxiv_reader_paper_cart_v1: JSON.stringify([{ id: '2611.1' }])
    }
    const g = globalThis as unknown as { localStorage?: unknown }
    g.localStorage = { getItem: (k: string) => data[k] ?? null, setItem: () => {} }
    const { initStores, prefs, prefsReady, saved } = await import('../../src/lib/store')
    initStores()
    expect(prefs.value).toEqual({ mode: 'dark', abs: 'zh', scope: 'primary', pageSize: 50 })
    expect(saved.value.map((x) => x.id)).toEqual(['2611.1'])
    expect(prefsReady.value).toBe(true)
    data.arxiv_reader_prefs_v2 = JSON.stringify({ pageSize: 33 })
    initStores()
    expect(prefs.value.pageSize).toBe(20)
    delete g.localStorage
  })
})
