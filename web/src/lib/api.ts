import type { DailyFile, Overview } from './types'

export class NotFound extends Error {}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url, { headers: { Accept: 'application/json' } })
  if (res.status === 404) throw new NotFound(url)
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`)
  return (await res.json()) as T
}

export const fetchOverview = () => getJson<Overview>('/api/overview')
export const fetchDates = () => getJson<{ dates: string[] }>('/api/dates').then((r) => r.dates)
export const fetchDaily = (date: string) => getJson<DailyFile>(`/api/daily/${date}`)

/** 记一次页面访问（首页、每日页各打开一次算一次） */
export function recordVisit(): void {
  fetch('/api/visit', { method: 'POST', keepalive: true }).catch(() => {})
}
