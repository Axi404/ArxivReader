/**
 * 页码条上显示哪些页：第一页、最后一页、当前页前后各 delta 页，中间跳过的是 null（显示成 …），
 * 和博客的分页一样；只跳过一页时直接显示那一页，不用省略号
 */
export function pageItems(current: number, last: number, delta = 2): (number | null)[] {
  if (last <= 1) return []
  const out: (number | null)[] = []
  let prev = 0
  for (let i = 1; i <= last; i++) {
    if (i !== 1 && i !== last && Math.abs(i - current) > delta) continue
    if (i - prev === 2) out.push(i - 1)
    else if (i - prev > 2) out.push(null)
    out.push(i)
    prev = i
  }
  return out
}

/** 地址里的 ?page=N；没有或不合法时是第 1 页 */
export function pageFromSearch(search: string): number {
  const n = Number(new URLSearchParams(search).get('page'))
  return Number.isInteger(n) && n >= 1 ? n : 1
}

export const pageHref = (n: number): string => (n <= 1 ? '/' : `/?page=${n}`)
