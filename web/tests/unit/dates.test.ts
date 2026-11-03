import { describe, expect, it } from 'vitest'
import { dateFromPath, monthLabel, weekdayOf } from '../../src/lib/dates'

describe('dates', () => {
  it('names the weekday of the date itself', () => {
    expect(weekdayOf('2026-11-03')).toBe('周二')
    expect(weekdayOf('2026-11-01')).toBe('周日')
  })
  it('labels months', () => {
    expect(monthLabel('2026-03')).toBe('2026 年 3 月')
  })
  it('reads the date from /daily/<date>', () => {
    expect(dateFromPath('/daily/2026-11-03')).toBe('2026-11-03')
    expect(dateFromPath('/daily/2026-11-03/')).toBe('2026-11-03')
    expect(dateFromPath('/daily/')).toBeNull()
    expect(dateFromPath('/daily/2026-11-3')).toBeNull()
  })
})
