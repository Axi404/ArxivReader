const WEEKDAYS = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/** '2026-11-03' -> '周二'（按日期本身算，不受时区影响） */
export function weekdayOf(day: string): string {
  const [y, m, d] = day.split('-').map(Number)
  return WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()] ?? ''
}

/** '2026-11' -> '2026 年 11 月' */
export const monthLabel = (month: string): string => `${month.slice(0, 4)} 年 ${Number(month.slice(5, 7))} 月`

export const DATE_RE = /^\d{4}-\d{2}-\d{2}$/

/** 每日页地址 /daily/<日期> 里的日期 */
export function dateFromPath(pathname: string): string | null {
  const m = pathname.match(/^\/daily\/(\d{4}-\d{2}-\d{2})\/?$/)
  return m ? m[1] : null
}
