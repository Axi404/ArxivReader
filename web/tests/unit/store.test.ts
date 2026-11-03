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
