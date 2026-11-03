// 手机宽度：不横向溢出，没有目录，搜索框落在顶栏下面，收藏抽屉打开时页面不滚
import { expect, test, type Page } from '@playwright/test'
import { mockApi, withPrefs } from './fixtures'

test.use({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true })

const noOverflow = (page: Page) => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('daily page fits the screen and has no TOC', async ({ page }) => {
  await withPrefs(page, { scope: 'all' })
  await page.goto('/daily/2026-11-03')
  await expect(page.locator('article').first()).toBeVisible()
  expect(await noOverflow(page)).toBe(true)
  await expect(page.locator('nav[aria-label="目录"]')).toBeHidden()
  const section = (await page.locator('#cat-cs-RO').boundingBox())!
  const logo = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  const star = (await page.locator('header').getByRole('button', { name: '收藏' }).boundingBox())!
  expect(Math.abs(logo.x - section.x)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(star.x + star.width - (section.x + section.width))).toBeLessThanOrEqual(0.5)
})

test('home page fits the screen', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '归档' })).toBeVisible()
  expect(await noOverflow(page)).toBe(true)
})

test('search box drops below the bar and stays on screen', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await page.locator('header').getByRole('button', { name: '搜索' }).tap()
  const box = page.getByPlaceholder('搜索')
  await expect(box).toBeFocused()
  const r = (await box.boundingBox())!
  const bar = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  expect(r.y).toBeGreaterThan(bar.y + bar.height)
  expect(r.x).toBeGreaterThanOrEqual(0)
  expect(r.x + r.width).toBeLessThanOrEqual(390)
  await box.fill('quadruped')
  await expect(page.locator('article')).toHaveCount(1)
})

test('saved drawer locks page scrolling while open', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await page.locator('header').getByRole('button', { name: '收藏' }).tap()
  const drawer = page.getByRole('complementary', { name: '收藏' })
  await expect(drawer).toBeVisible()
  await expect(page.locator('html')).toHaveClass(/lock/)
  await drawer.getByRole('button', { name: '关闭' }).tap()
  await expect(drawer).toBeHidden()
  await expect(page.locator('html')).not.toHaveClass(/lock/)
})
