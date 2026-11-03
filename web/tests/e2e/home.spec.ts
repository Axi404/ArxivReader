// 首页：最新一期、统计、归档，以及访问计数
import { expect, test, type Page } from '@playwright/test'
import { mockApi, overviewWithDays, settle, withPrefs } from './fixtures'

test('latest day, stats and the archive by month', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const latest = page.locator('section', { has: page.getByRole('heading', { name: '最新' }) })
  await expect(latest).toContainText('2026-11-03')
  await expect(latest).toContainText('周二')
  const rows = await latest.locator('tbody tr').evaluateAll((trs) => trs.map((tr) => [...tr.querySelectorAll('td')].map((td) => td.textContent?.trim())))
  expect(rows).toEqual([
    ['cs.RO机器人学', '10', '4', '13'],
    ['cs.CV计算机视觉', '6', '0', '6'],
    ['cs.AI人工智能', '3', '0', '3'],
    ['cs.CL计算语言学', '1', '0', '1']
  ])

  const stats = page.locator('section', { has: page.getByRole('heading', { name: '统计' }) })
  await expect(stats).toContainText('3天数')
  await expect(stats).toContainText('1234论文')
  await expect(stats).toContainText('5今日访问')
  await expect(stats).toContainText('678累计访问')

  const archive = page.locator('section', { has: page.getByRole('heading', { name: '归档' }) })
  await expect(archive.locator('h4')).toHaveText(['2026 年 11 月', '2026 年 10 月'])
  const hrefs = await archive.getByRole('link').evaluateAll((as) => as.map((a) => a.getAttribute('href')))
  expect(hrefs).toEqual(['/daily/2026-11-03', '/daily/2026-11-02', '/daily/2026-10-30'])
  await expect(archive.getByRole('link').first()).toContainText('cs.RO14')

  await latest.getByRole('link', { name: '阅读' }).click()
  await expect(page).toHaveURL(/\/daily\/2026-11-03$/)
})

test('category rows open the daily page at that category', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByRole('link', { name: 'cs.AI', exact: true }).click()
  await expect(page).toHaveURL(/\/daily\/2026-11-03#cat-cs-AI$/)
  await expect(page.locator('#cat-cs-AI')).toBeVisible()
  await settle(page)
  const top = await page.locator('#cat-cs-AI').evaluate((el) => el.getBoundingClientRect().top)
  expect(Math.abs(top - 90)).toBeLessThanOrEqual(1.5)
})

test('each page load records one visit', async ({ page }) => {
  const api = await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '最新' })).toBeVisible()
  await expect.poll(() => api.visits.length).toBe(1)
  await page.goto('/daily/2026-11-03')
  await expect(page.locator('article').first()).toBeVisible()
  await expect.poll(() => api.visits.length).toBe(2)
})

test('header and blocks share one column', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  const heading = (await page.getByRole('heading', { name: '最新' }).boundingBox())!
  const logo = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  const star = (await page.locator('header').getByRole('button', { name: '收藏' }).boundingBox())!
  const card = (await page.locator('section', { has: page.getByRole('heading', { name: '最新' }) }).locator('.rounded-xl').first().boundingBox())!
  expect(Math.abs(logo.x - heading.x)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(star.x + star.width - (card.x + card.width))).toBeLessThanOrEqual(0.5)
})

test('unknown paths get the 404 page with a way home', async ({ page }) => {
  await mockApi(page)
  const res = await page.goto('/no-such-page')
  expect(res?.status()).toBe(404)
  await expect(page.getByText('404', { exact: true })).toBeVisible()
  const logo = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  await page.goto('/')
  const home = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  expect(logo).toEqual(home)
  await page.goto('/no-such-page')
  await page.getByRole('link', { name: '首页' }).click()
  await expect(page).toHaveURL(/\/$/)
})

// ---- 归档分页 ----

const archive = (page: Page) => page.locator('#archive')
const rows = (page: Page) => archive(page).locator('a[href^="/daily/"]')
const pager = (page: Page) => page.getByRole('navigation', { name: '分页' })
// 页码条上除了左右箭头以外的每一项：数字或 …
const pageList = (page: Page) => pager(page).locator(':scope > *').evaluateAll((els) => els.filter((e) => !e.querySelector('svg')).map((e) => e.textContent))
const monthOf = (date: string) => `${date.slice(0, 4)} 年 ${Number(date.slice(5, 7))} 月`

test('the archive is split into pages; numbers, arrows, the address and Back agree', async ({ page }) => {
  const o = overviewWithDays(45)
  await mockApi(page, { overview: o })
  await page.goto('/')
  await expect(rows(page)).toHaveCount(20)
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[0].date}`)
  expect(await pageList(page)).toEqual(['1', '2', '3'])
  await expect(pager(page).locator('[aria-current="page"]')).toHaveText('1')
  await expect(pager(page).getByRole('link', { name: '上一页' })).toHaveCount(0)

  await pager(page).getByRole('link', { name: '2', exact: true }).click()
  await expect(page).toHaveURL(/\/\?page=2$/)
  await expect(rows(page)).toHaveCount(20)
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[20].date}`)
  await expect(archive(page).locator('h4').first()).toHaveText(monthOf(o.days[20].date))
  await expect(pager(page).locator('[aria-current="page"]')).toHaveText('2')

  await pager(page).getByRole('link', { name: '下一页' }).click()
  await expect(page).toHaveURL(/\/\?page=3$/)
  await expect(rows(page)).toHaveCount(5)
  await expect(pager(page).getByRole('link', { name: '下一页' })).toHaveCount(0)

  await page.goBack()
  await expect(page).toHaveURL(/\/\?page=2$/)
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[20].date}`)
  await page.goBack()
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[0].date}`)
  await page.goForward()
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[20].date}`)
})

test('a page in the address opens directly; past the end goes to the last page', async ({ page }) => {
  await mockApi(page, { overview: overviewWithDays(45) })
  await page.goto('/?page=3')
  await expect(rows(page)).toHaveCount(5)
  await page.goto('/?page=99')
  await expect(page).toHaveURL(/\/\?page=3$/)
  await expect(rows(page)).toHaveCount(5)
})

test('page size is a setting, is remembered, and keeps your place', async ({ page }) => {
  const o = overviewWithDays(45)
  await mockApi(page, { overview: o })
  await page.goto('/?page=3')
  await expect(rows(page)).toHaveCount(5)
  await page.locator('header').getByRole('button', { name: '设置' }).click()
  const settings = page.getByRole('dialog', { name: '设置' })
  await expect(settings.getByRole('button', { name: '20', exact: true })).toHaveAttribute('aria-pressed', 'true')

  // 第 3 页从第 41 天开始；改成每页 10 天，第 41 天在第 5 页
  await settings.getByRole('button', { name: '10', exact: true }).click()
  await expect(page).toHaveURL(/\/\?page=5$/)
  await expect(rows(page)).toHaveCount(5)
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[40].date}`)

  await settings.getByRole('button', { name: '50', exact: true }).click()
  await expect(page).toHaveURL(/\/$/)
  await expect(rows(page)).toHaveCount(45)
  await expect(pager(page)).toHaveCount(0)

  await page.reload()
  await expect(rows(page)).toHaveCount(45)
})

test('a stored page size applies to the page in the address', async ({ page }) => {
  const o = overviewWithDays(45)
  await mockApi(page, { overview: o })
  await withPrefs(page, { pageSize: 10 })
  await page.goto('/?page=3')
  await expect(rows(page)).toHaveCount(10)
  await expect(rows(page).first()).toHaveAttribute('href', `/daily/${o.days[20].date}`)
  await expect(page).toHaveURL(/\/\?page=3$/)
  await expect(pager(page).locator('[aria-current="page"]')).toHaveText('3')
})

test('long archives show the first, the last and the pages around the current one', async ({ page }) => {
  await mockApi(page, { overview: overviewWithDays(191) })
  await withPrefs(page, { pageSize: 10 })
  await page.goto('/?page=10')
  await expect(pager(page).locator('[aria-current="page"]')).toHaveText('10')
  expect(await pageList(page)).toEqual(['1', '…', '8', '9', '10', '11', '12', '…', '20'])
})

test('changing page from the bottom of the list goes back to the start of the archive', async ({ page }) => {
  await mockApi(page, { overview: overviewWithDays(45) })
  await page.goto('/')
  const two = pager(page).getByRole('link', { name: '2', exact: true })
  await two.scrollIntoViewIfNeeded()
  expect(await archive(page).evaluate((el) => el.getBoundingClientRect().top)).toBeLessThan(0)
  await two.click()
  await settle(page)
  const top = await archive(page).evaluate((el) => el.getBoundingClientRect().top)
  expect(Math.abs(top - 90)).toBeLessThanOrEqual(1.5)
})
