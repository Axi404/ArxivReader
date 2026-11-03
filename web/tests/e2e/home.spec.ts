// 首页：最新一期、统计、归档，以及访问计数
import { expect, test } from '@playwright/test'
import { mockApi, settle } from './fixtures'

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
