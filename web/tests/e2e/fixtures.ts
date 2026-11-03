// e2e 用的假数据和假接口：页面只认 /api，测试里直接拦下来回这些 JSON，不用起后端
import { expect, type Page } from '@playwright/test'

type Kind = 'new' | 'cross'
interface Paper {
  arxiv_id: string
  title: string
  authors: string[]
  abstract: string
  title_zh: string | null
  abstract_zh: string | null
  comments: string | null
  primary_category: string
  kind?: Kind
}

const EN =
  'We present a method for learning manipulation skills from large and diverse demonstration data. ' +
  'The approach scales with data and compute, transfers across embodiments, and is evaluated on a broad suite of tasks in simulation and on real robots. ' +
  'Ablations isolate the contribution of each component and show where the gains come from.'
const ZH = '我们提出一种从大规模、多样化示范数据中学习操作技能的方法。该方法随数据和算力扩展，能迁移到不同本体，并在仿真和真机的大量任务上评测。消融实验分离了每个部分的贡献。'

function paper(id: string, primary: string, kind: Kind | undefined, extra: Partial<Paper> = {}): Paper {
  return {
    arxiv_id: id,
    title: `Paper ${id}: Scaling Robot Learning`,
    authors: ['Alice Zhang', 'Bob Li', 'Carol Wang'],
    abstract: EN,
    title_zh: `论文 ${id}：扩展机器人学习`,
    abstract_zh: ZH,
    comments: '8 pages, 4 figures',
    primary_category: primary,
    ...(kind ? { kind } : {}),
    ...extra
  }
}

const range = (n: number, f: (i: number) => Paper) => Array.from({ length: n }, (_, i) => f(i))

// 11-03：cs.RO 10 篇新提交 + 4 篇 cross-list，cs.CV 6 篇，cs.AI 3 篇，cs.CL 1 篇（最后一块很短，目录点它时页面滚不到落点）
const CV_CROSS = paper('2611.00482', 'cs.CV', 'cross', { title: 'Vision Paper Also Listed in Robotics' })
export const DAY_1103 = {
  date: '2026-11-03',
  format: 2,
  papers_by_category: {
    'cs.RO': [
      paper('2611.00101', 'cs.RO', 'new', {
        title: 'Diffusion Policies for Quadruped Manipulation',
        abstract: 'We train \\emph{diffusion} policies with 50\\% fewer steps. Code: https://example.com/code. ' + EN,
        comments: '8 pages. Project page: https://example.org/proj.'
      }),
      paper('2611.00102', 'cs.RO', 'new', { title_zh: null, abstract_zh: null, title: 'Untranslated Robot Paper' }),
      ...range(8, (i) => paper(`2611.0011${i}`, 'cs.RO', 'new')),
      paper('2611.00231', 'eess.SY', 'cross', { title: 'Quadruped Control with Calibrated Intervals' }),
      paper('2611.00232', 'cs.LG', 'cross'),
      paper('2611.00233', 'cs.HC', 'cross'),
      CV_CROSS
    ],
    'cs.CV': [{ ...CV_CROSS, kind: 'new' as const }, ...range(5, (i) => paper(`2611.0030${i}`, 'cs.CV', 'new'))],
    'cs.AI': range(3, (i) => paper(`2611.0040${i}`, 'cs.AI', 'new')),
    'cs.CL': [paper('2611.00500', 'cs.CL', 'new')]
  }
}

// 11-02 是旧格式：没有 kind 字段，全算新提交
export const DAY_1102 = {
  date: '2026-11-02',
  papers_by_category: {
    'cs.RO': range(3, (i) => paper(`2610.0990${i}`, 'cs.RO', undefined)),
    'cs.CV': range(2, (i) => paper(`2610.0980${i}`, 'cs.CV', undefined))
  }
}

export const DAY_1030 = {
  date: '2026-10-30',
  format: 2,
  papers_by_category: { 'cs.RO': range(2, (i) => paper(`2610.0880${i}`, 'cs.RO', 'new')) }
}

const DAILY: Record<string, unknown> = { '2026-11-03': DAY_1103, '2026-11-02': DAY_1102, '2026-10-30': DAY_1030 }
export const DATES = ['2026-11-03', '2026-11-02', '2026-10-30']

export const OVERVIEW = {
  days: [
    {
      date: '2026-11-03',
      summary: {
        total: 23,
        new: 20,
        cross: 4,
        translated: 23,
        categories: [
          { code: 'cs.RO', new: 10, cross: 4, translated: 13 },
          { code: 'cs.CV', new: 6, cross: 0, translated: 6 },
          { code: 'cs.AI', new: 3, cross: 0, translated: 3 },
          { code: 'cs.CL', new: 1, cross: 0, translated: 1 }
        ]
      }
    },
    {
      date: '2026-11-02',
      summary: {
        total: 5,
        new: 5,
        cross: 0,
        translated: 5,
        categories: [
          { code: 'cs.RO', new: 3, cross: 0, translated: 3 },
          { code: 'cs.CV', new: 2, cross: 0, translated: 2 }
        ]
      }
    },
    { date: '2026-10-30', summary: null }
  ],
  stats: { days: 3, papers: 1234 },
  traffic: { daily: 5, total: 678 }
}

/** 拦下 /api：返回上面的数据，记下访问计数的请求；failDaily 时某一天的数据返回 500 */
export async function mockApi(page: Page, opts: { failDaily?: string } = {}) {
  const visits: string[] = []
  await page.route('**/api/**', async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname
    if (path === '/api/visit') {
      expect(route.request().method()).toBe('POST')
      visits.push(page.url())
      return route.fulfill({ json: { ok: true } })
    }
    if (path === '/api/dates') return route.fulfill({ json: { dates: DATES, total: DATES.length } })
    if (path === '/api/overview') return route.fulfill({ json: OVERVIEW })
    const day = path.match(/^\/api\/daily\/(\d{4}-\d{2}-\d{2})$/)?.[1]
    if (day && day === opts.failDaily) return route.fulfill({ status: 500, body: 'boom' })
    if (day && DAILY[day]) return route.fulfill({ json: DAILY[day] })
    return route.fulfill({ status: 404, json: { detail: 'not found' } })
  })
  return { visits }
}

/** 先在浏览器里存好设置（范围、摘要、主题），再打开页面 */
export async function withPrefs(page: Page, prefs: Record<string, string>) {
  await page.addInitScript((p) => {
    if (!sessionStorage.getItem('prefs-seeded')) {
      localStorage.setItem('arxiv_reader_prefs_v2', JSON.stringify(p))
      sessionStorage.setItem('prefs-seeded', '1')
    }
  }, prefs)
}

/** 等页面停止滚动（连续几帧 scrollY 不变），再多等两帧让目录跟上 */
export async function settle(page: Page) {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        let last = window.scrollY
        let still = 0
        const tick = () => {
          if (window.scrollY === last) still += 1
          else {
            still = 0
            last = window.scrollY
          }
          if (still >= 6) resolve()
          else requestAnimationFrame(tick)
        }
        requestAnimationFrame(tick)
      })
  )
  await page.waitForTimeout(80)
}
