import { describe, expect, it } from 'vitest'
import { pageFromSearch, pageHref, pageItems } from '../../src/lib/pages'

describe('pageItems', () => {
  it('shows nothing for a single page and every page for a few', () => {
    expect(pageItems(1, 1)).toEqual([])
    expect(pageItems(2, 3)).toEqual([1, 2, 3])
  })
  it('keeps the first, the last and two pages around the current one', () => {
    expect(pageItems(1, 20)).toEqual([1, 2, 3, null, 20])
    expect(pageItems(10, 20)).toEqual([1, null, 8, 9, 10, 11, 12, null, 20])
    expect(pageItems(20, 20)).toEqual([1, null, 18, 19, 20])
  })
  it('shows a single skipped page instead of an ellipsis', () => {
    expect(pageItems(5, 20)).toEqual([1, 2, 3, 4, 5, 6, 7, null, 20])
    expect(pageItems(16, 20)).toEqual([1, null, 14, 15, 16, 17, 18, 19, 20])
  })
  it('narrows to one page around the current one when asked', () => {
    expect(pageItems(10, 20, 1)).toEqual([1, null, 9, 10, 11, null, 20])
  })
})

describe('page in the address', () => {
  it('reads ?page=N and falls back to the first page', () => {
    expect(pageFromSearch('?page=3')).toBe(3)
    expect(pageFromSearch('')).toBe(1)
    expect(pageFromSearch('?page=0')).toBe(1)
    expect(pageFromSearch('?page=2.5')).toBe(1)
    expect(pageFromSearch('?page=abc')).toBe(1)
  })
  it('writes the first page as /', () => {
    expect(pageHref(1)).toBe('/')
    expect(pageHref(4)).toBe('/?page=4')
  })
})
