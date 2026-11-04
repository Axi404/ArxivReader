// 每日页：日期切换、日历、范围、搜索、收藏、摘要、主题、文字处理、出错时的样子、顶栏和正文对齐
import { expect, test, type Page } from '@playwright/test'
import { mockApi, withPrefs } from './fixtures'

const header = (page: Page) => page.locator('header')
const savedButton = (page: Page) => header(page).getByRole('button', { name: '收藏' })
const cards = (page: Page) => page.locator('article')

async function openSettings(page: Page) {
  await header(page).getByRole('button', { name: '设置' }).click()
  return page.getByRole('dialog', { name: '设置' })
}

test.beforeEach(async ({ page }) => {
  await mockApi(page)
})

test('date heading, weekday and previous/next day buttons', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await expect(page.locator('h1')).toHaveText(/2026-11-03\s*周二/)
  await expect(page).toHaveTitle('2026-11-03 · arXiv Reader')
  await expect(page.getByRole('link', { name: '后一天' })).toHaveCount(0)
  await page.getByRole('link', { name: '前一天' }).click()
  await expect(page).toHaveURL(/\/daily\/2026-11-02$/)
  await expect(page.locator('h1')).toHaveText(/2026-11-02\s*周一/)
  await expect(page.getByRole('link', { name: '前一天' })).toHaveAttribute('href', '/daily/2026-10-30')
  await expect(page.getByRole('link', { name: '后一天' })).toHaveAttribute('href', '/daily/2026-11-03')
})

test('calendar: days with data are links, today is marked, months page through the data', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await page.getByRole('button', { name: '选日期' }).click()
  const cal = page.getByRole('dialog', { name: '日历' })
  await expect(cal).toContainText('2026 年 11 月')
  await expect(cal.locator('[aria-current="date"]')).toHaveText('3')
  await expect(cal.getByRole('link')).toHaveCount(1)
  await expect(cal.getByRole('link', { name: '2', exact: true })).toHaveAttribute('href', '/daily/2026-11-02')
  await expect(cal.getByRole('button', { name: '下个月' })).toBeDisabled()

  await cal.getByRole('button', { name: '上个月' }).click()
  await expect(cal).toContainText('2026 年 10 月')
  await expect(cal.getByRole('button', { name: '上个月' })).toBeDisabled()
  await expect(cal.getByRole('link')).toHaveCount(1)
  await cal.getByRole('link', { name: '30', exact: true }).click()
  await expect(page).toHaveURL(/\/daily\/2026-10-30$/)
  await expect(page.locator('h1')).toHaveText(/2026-10-30\s*周五/)
})

test('calendar and settings close on Escape and on an outside click', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await page.getByRole('button', { name: '选日期' }).click()
  await expect(page.getByRole('dialog', { name: '日历' })).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name: '日历' })).toHaveCount(0)

  const settings = await openSettings(page)
  await expect(settings).toBeVisible()
  await page.mouse.click(30, 600)
  await expect(settings).toHaveCount(0)
})

test('scope decides which papers, counts and sections show, and is remembered', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await expect(cards(page)).toHaveCount(20)
  await expect(page.locator('main')).toContainText('新提交 20')
  await expect(page.locator('#cat-cs-RO-cross')).toHaveCount(0)
  await expect(page.locator('article .rounded-full', { hasText: 'cross-list' })).toHaveCount(0)

  const settings = await openSettings(page)
  await settings.getByRole('button', { name: 'cross-list' }).click()
  await expect(cards(page)).toHaveCount(4)
  await expect(page.locator('#cat-cs-RO')).toContainText('cross-list 4')
  await expect(page.locator('#cat-cs-RO')).not.toContainText('新提交')

  await settings.getByRole('button', { name: '全部' }).click()
  await expect(cards(page)).toHaveCount(24)
  await expect(page.locator('#cat-cs-RO-cross')).toBeVisible()
  await expect(page.locator('#cat-cs-RO')).toContainText('新提交 10')
  await expect(page.locator('#cat-cs-RO')).toContainText('cross-list 4')
  await expect(settings.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')

  await page.reload()
  await expect(cards(page)).toHaveCount(24)
  const again = await openSettings(page)
  await expect(again.getByRole('button', { name: '全部' })).toHaveAttribute('aria-pressed', 'true')
})

test('cross-list cards show their primary category', async ({ page }) => {
  await withPrefs(page, { scope: 'cross' })
  await page.goto('/daily/2026-11-03')
  const card = page.locator('article[data-id="2611.00231"]')
  await expect(card).toContainText('cross-list')
  await expect(card).toContainText('eess.SY')
})

test('days stored in the old format list everything as new submissions', async ({ page }) => {
  await withPrefs(page, { scope: 'all' })
  await page.goto('/daily/2026-11-02')
  await expect(cards(page)).toHaveCount(5)
  await expect(page.locator('main')).toContainText('cross-list 0')
  await expect(page.locator('[id$="-cross"]')).toHaveCount(0)
})

test('search: "/" opens it, it filters cards, counts and the TOC, Escape clears it', async ({ page }) => {
  await withPrefs(page, { scope: 'all' })
  await page.goto('/daily/2026-11-03')
  await expect(cards(page)).toHaveCount(24)
  await page.keyboard.press('/')
  const box = page.getByPlaceholder('搜索')
  await expect(box).toBeFocused()
  await box.fill('quadruped')
  await expect(cards(page)).toHaveCount(2)
  await expect(header(page)).toContainText('2 篇')
  await expect(page.locator('#cat-cs-RO')).toContainText('新提交 1')
  await expect(page.locator('#cat-cs-RO')).toContainText('cross-list 1')
  const toc = await page.locator('nav[aria-label="目录"] a').evaluateAll((as) => as.map((a) => a.textContent))
  expect(toc).toEqual(['cs.RO1', 'cross-list1', 'cs.CV0', 'cs.AI0', 'cs.CL0'])

  await box.fill('2611.00482')
  await expect(cards(page)).toHaveCount(2)
  await box.fill('quadruped intervals')
  await expect(cards(page)).toHaveCount(1)
  await box.fill('nothing-like-this')
  await expect(cards(page)).toHaveCount(0)
  await expect(header(page)).toContainText('0 篇')

  await box.press('Escape')
  await expect(box).toHaveCount(0)
  await expect(cards(page)).toHaveCount(24)
})

test('typing right after "/" goes into the search box', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  await expect(cards(page)).toHaveCount(20)
  await page.keyboard.press('/')
  await page.keyboard.type('quadruped manipulation')
  await expect(page.getByPlaceholder('搜索')).toHaveValue('quadruped manipulation')
  await expect(cards(page)).toHaveCount(1)
  expect(await page.evaluate(() => window.scrollY)).toBe(0)
})

test('saved papers: star anywhere, persists across reloads and days, drawer copies and removes', async ({ page, context, browserName }) => {
  await withPrefs(page, { scope: 'all' })
  await page.goto('/daily/2026-11-03')
  const both = page.locator('article[data-id="2611.00482"]')
  await expect(both).toHaveCount(2)
  await both.first().getByRole('button', { name: '收藏' }).click()
  for (const k of [0, 1]) await expect(both.nth(k).getByRole('button', { name: '收藏' })).toHaveAttribute('aria-pressed', 'true')
  await page.locator('article[data-id="2611.00101"]').getByRole('button', { name: '收藏' }).click()
  await expect(savedButton(page)).toHaveText('2')

  await page.reload()
  await expect(savedButton(page)).toHaveText('2')
  await page.goto('/daily/2026-11-02')
  await expect(savedButton(page)).toHaveText('2')

  await savedButton(page).click()
  const drawer = page.getByRole('complementary', { name: '收藏' })
  await expect(drawer).toBeVisible()
  await expect(drawer).toContainText('Vision Paper Also Listed in Robotics')
  await expect(drawer).toContainText('2611.00482 · 2026-11-03')

  if (browserName === 'chromium') {
    await context.grantPermissions(['clipboard-read', 'clipboard-write'])
    await drawer.getByRole('button', { name: '复制 ID', exact: true }).click()
    await expect(page.getByText('已复制 2 篇')).toBeVisible()
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe('2611.00482\n2611.00101')
  }

  await drawer.getByRole('button', { name: '移除' }).first().click()
  await expect(savedButton(page)).toHaveText('1')
  page.once('dialog', (d) => d.accept())
  await drawer.getByRole('button', { name: '清空' }).click()
  await expect(savedButton(page)).toHaveText('')
  await page.keyboard.press('Escape')
  await expect(drawer).toBeHidden()
})

test('saved papers follow changes made in another tab', async ({ page, context }) => {
  await page.goto('/daily/2026-11-03')
  await expect(cards(page).first()).toBeVisible()
  const other = await context.newPage()
  await mockApi(other)
  await other.goto('/daily/2026-11-03')
  await other.locator('article[data-id="2611.00101"]').getByRole('button', { name: '收藏' }).click()
  await expect(savedButton(page)).toHaveText('1')
  await expect(page.locator('article[data-id="2611.00101"]').getByRole('button', { name: '收藏' })).toHaveAttribute('aria-pressed', 'true')
})

test('abstracts: both, Chinese, English, or hidden behind a toggle', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const card = page.locator('article[data-id="2611.00110"]')
  const en = 'We present a method'
  const zh = '我们提出一种'
  await expect(card).toContainText(en)
  await expect(card).toContainText(zh)

  const settings = await openSettings(page)
  await settings.getByRole('button', { name: '中文', exact: true }).click()
  await expect(card).not.toContainText(en)
  await expect(card).toContainText(zh)
  await settings.getByRole('button', { name: '英文', exact: true }).click()
  await expect(card).toContainText(en)
  await expect(card).not.toContainText(zh)
  await settings.getByRole('button', { name: '不显示' }).click()
  await page.keyboard.press('Escape')
  await expect(card).not.toContainText(en)
  await card.getByRole('button', { name: '摘要' }).click()
  await expect(card).toContainText(en)
  await expect(card).toContainText(zh)
})

test('TeX markup is cleaned up and URLs become links', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const card = page.locator('article[data-id="2611.00101"]')
  await expect(card).toContainText('We train diffusion policies with 50% fewer steps.')
  await expect(card).not.toContainText('\\emph')
  await expect(card.getByRole('link', { name: 'https://example.com/code' })).toHaveAttribute('href', 'https://example.com/code')
  await expect(card.getByRole('link', { name: 'https://example.org/proj' })).toHaveAttribute('href', 'https://example.org/proj')
  await expect(card.getByRole('link', { name: 'PDF' })).toHaveAttribute('href', 'https://arxiv.org/pdf/2611.00101')
})

test('formulas are typeset with KaTeX; ones it cannot typeset stay as written', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const card = page.locator('article[data-id="2611.00101"]')
  const en = card.locator('p', { hasText: 'We train' })
  await expect(en.locator('.katex')).toHaveCount(3)
  await expect(en.locator('.katex-display')).toHaveCount(1)
  await expect(en.locator('.katex-html').first()).toHaveText('×')
  await expect(en).toContainText('our $\\notdefined{x}$ stays as written')
  // 存下来的中文里被 JSON 吃掉的反斜杠（\t、\b）补回来以后照样能排
  const zh = card.locator('p', { hasText: '我们训练' })
  await expect(zh.locator('.katex-html')).toHaveText(['×', 'β'])

  const titled = page.locator('article[data-id="2611.00111"]')
  await expect(titled.locator('h3 .katex')).toHaveCount(2)
  await expect(titled.locator('h3 a')).toHaveAttribute('href', 'https://arxiv.org/abs/2611.00111')
  await expect(titled.locator('h3 + p .katex')).toHaveCount(2)
  expect(await card.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
})

test('copying text with formulas gives their LaTeX', async ({ page, context, browserName }) => {
  test.skip(browserName !== 'chromium', 'reading the clipboard needs Chromium permissions')
  await context.grantPermissions(['clipboard-read', 'clipboard-write'])
  await page.goto('/daily/2026-11-03')
  const zh = page.locator('article[data-id="2611.00101"] p', { hasText: '我们训练' })
  await expect(zh.locator('.katex')).toHaveCount(2)
  await zh.evaluate((el) => {
    const range = document.createRange()
    range.selectNodeContents(el)
    const selection = getSelection()!
    selection.removeAllRanges()
    selection.addRange(range)
    document.execCommand('copy')
  })
  const text = await page.evaluate(() => navigator.clipboard.readText())
  expect(text).toContain('速度快 2$\\times$，$\\beta$ 更小')
})

test('untranslated papers show only the original text', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const card = page.locator('article[data-id="2611.00102"]')
  await expect(card.locator('h3')).toHaveText('Untranslated Robot Paper')
  await expect(card.locator('h3 + p')).not.toContainText('论文')
})

test('dark theme is set before any script runs, and auto follows the system', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const settings = await openSettings(page)
  await settings.getByRole('button', { name: '深色' }).click()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await settings.getByRole('button', { name: '浅色' }).click()
  await expect(page.locator('html')).not.toHaveClass(/dark/)
  await settings.getByRole('button', { name: '深色' }).click()

  // 页面脚本全部拦掉，只剩 head 里那一小段：深色照样生效
  await page.route('**/_astro/**', (r) => r.abort())
  await page.reload()
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.unroute('**/_astro/**')

  await page.reload()
  const s2 = await openSettings(page)
  await s2.getByRole('button', { name: '自动' }).click()
  await page.emulateMedia({ colorScheme: 'dark' })
  await expect(page.locator('html')).toHaveClass(/dark/)
  await page.emulateMedia({ colorScheme: 'light' })
  await expect(page.locator('html')).not.toHaveClass(/dark/)
})

test('a day without data says so; a failed request says it failed', async ({ page }) => {
  await page.goto('/daily/2026-01-01')
  await expect(page.locator('main')).toContainText('没有 2026-01-01 的数据')
  await page.unrouteAll()
  await mockApi(page, { failDaily: '2026-11-03' })
  await page.goto('/daily/2026-11-03')
  await expect(page.locator('main')).toContainText('加载失败')
})

test('header and content share one column; the TOC sits in the right margin', async ({ page }) => {
  await page.goto('/daily/2026-11-03')
  const section = (await page.locator('#cat-cs-RO').boundingBox())!
  const logo = (await page.getByRole('link', { name: 'arXiv Reader' }).boundingBox())!
  const date = (await page.getByRole('button', { name: '选日期' }).boundingBox())!
  const star = (await savedButton(page).boundingBox())!
  const toc = (await page.locator('nav[aria-label="目录"]').boundingBox())!
  expect(Math.abs(logo.x - section.x)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(date.x - section.x)).toBeLessThanOrEqual(0.5)
  expect(Math.abs(star.x + star.width - (section.x + section.width))).toBeLessThanOrEqual(0.5)
  // 正文在窗口正中
  const vw = page.viewportSize()!.width
  expect(Math.abs(section.x + section.width / 2 - vw / 2)).toBeLessThanOrEqual(0.5)
  expect(toc.x).toBeGreaterThan(section.x + section.width)
})
