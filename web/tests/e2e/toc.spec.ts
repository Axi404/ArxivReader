// 目录：三种范围下每一项都点一遍（正着点再倒着点），落点在顶栏下面 90px（页面滚不到时就在最底下），点过的那一项一直标着；
// 手动滚过每一块的边界时，标出的项跟着变
import { expect, test, type Page } from '@playwright/test'
import { mockApi, settle, withPrefs } from './fixtures'

const LANDING = 90 // html 的 scroll-padding-top
const LINE = 110 // Toc.tsx 里的 LINE

const links = (page: Page) => page.locator('nav[aria-label="目录"] a')
const current = (page: Page) => links(page).evaluateAll((as) => as.findIndex((a) => a.getAttribute('aria-current') === 'location'))

async function expectCurrent(page: Page, k: number) {
  await expect(links(page).nth(k)).toHaveAttribute('aria-current', 'location')
  await expect(page.locator('nav[aria-label="目录"] a[aria-current]')).toHaveCount(1)
}

async function landing(page: Page, id: string) {
  return page.evaluate((id) => {
    const el = document.getElementById(id)
    if (!el) throw new Error(`no #${id}`)
    const max = document.documentElement.scrollHeight - window.innerHeight
    return { top: el.getBoundingClientRect().top, atBottom: window.scrollY >= max - 1 }
  }, id)
}

async function expectLanded(page: Page, id: string) {
  const r = await landing(page, id)
  if (r.atBottom && r.top > LANDING + 1) return // 最后几块太短，页面已经滚到底
  expect(Math.abs(r.top - LANDING), `#${id} top ${r.top}`).toBeLessThanOrEqual(1.5)
}

const ITEMS = {
  primary: [['cs.RO', '10'], ['cs.CV', '6'], ['cs.AI', '3'], ['cs.CL', '1']],
  cross: [['cs.RO', '4'], ['cs.CV', '0'], ['cs.AI', '0'], ['cs.CL', '0']],
  all: [['cs.RO', '10'], ['cross-list', '4'], ['cs.CV', '6'], ['cs.AI', '3'], ['cs.CL', '1']]
} as const

for (const scope of ['primary', 'cross', 'all'] as const) {
  test(`${scope}: every item jumps to its section and stays highlighted, forward and back`, async ({ page }) => {
    await mockApi(page)
    await withPrefs(page, { scope })
    await page.goto('/daily/2026-11-03')
    await expect(links(page)).toHaveCount(ITEMS[scope].length)
    const texts = await links(page).evaluateAll((as) => as.map((a) => [...a.querySelectorAll('span')].map((s) => s.textContent)))
    expect(texts).toEqual(ITEMS[scope])
    await expectCurrent(page, 0)

    const n = ITEMS[scope].length
    const order = [...Array(n).keys(), ...[...Array(n - 1).keys()].reverse()]
    for (const k of order) {
      const link = links(page).nth(k)
      const id = (await link.getAttribute('href'))!.slice(1)
      await link.click()
      await settle(page)
      await expectLanded(page, id)
      await expectCurrent(page, k)
      await expect(page).toHaveURL(new RegExp(`#${id}$`))
    }
  })
}

test('manual scrolling moves the highlight at each section boundary', async ({ page }) => {
  await mockApi(page)
  await withPrefs(page, { scope: 'all' })
  await page.goto('/daily/2026-11-03')
  await expect(links(page)).toHaveCount(5)
  const ids = await links(page).evaluateAll((as) => as.map((a) => a.getAttribute('href')!.slice(1)))
  const last = ids.length - 1

  // 把第 k 块的顶边放到离窗口顶 offset 的地方；返回页面是不是因此到了底
  const place = (id: string, offset: number) =>
    page.evaluate(
      ([id, offset]) => {
        const el = document.getElementById(id as string)!
        const y = el.getBoundingClientRect().top + window.scrollY - (offset as number)
        window.scrollTo(0, y)
        const max = document.documentElement.scrollHeight - window.innerHeight
        return Math.min(y, max) >= max - 4
      },
      [id, offset]
    )

  for (let k = 0; k < ids.length; k++) {
    const bottom = await place(ids[k], LINE - 10)
    await settle(page)
    await expectCurrent(page, bottom ? last : k)
    if (k > 0) {
      const bottom2 = await place(ids[k], LINE + 20)
      await settle(page)
      await expectCurrent(page, bottom2 ? last : k - 1)
    }
  }
  await page.evaluate(() => window.scrollTo(0, 0))
  await settle(page)
  await expectCurrent(page, 0)
})

test('opening a link with #section scrolls there once the data has loaded', async ({ page }) => {
  await mockApi(page)
  await page.goto('/daily/2026-11-03#cat-cs-AI')
  await expect(page.locator('#cat-cs-AI')).toBeVisible()
  await settle(page)
  await expectLanded(page, 'cat-cs-AI')
  await expectCurrent(page, 2)
})

test.describe('smooth scrolling', () => {
  test.use({ reducedMotion: 'no-preference' })

  test('the clicked item stays highlighted for the whole scroll', async ({ page }) => {
    await mockApi(page)
    await withPrefs(page, { scope: 'all' })
    await page.goto('/daily/2026-11-03')
    await expect(links(page)).toHaveCount(5)

    await links(page).nth(4).click()
    for (let i = 0; i < 8; i++) {
      expect(await current(page)).toBe(4)
      await page.waitForTimeout(60)
    }
    await settle(page)
    await expectCurrent(page, 4)

    await links(page).nth(1).click()
    await settle(page)
    await expectLanded(page, 'cat-cs-RO-cross')
    await expectCurrent(page, 1)
  })

  test('clicking another item mid-scroll ends on the second item', async ({ page }) => {
    await mockApi(page)
    await withPrefs(page, { scope: 'all' })
    await page.goto('/daily/2026-11-03')
    await expect(links(page)).toHaveCount(5)

    await links(page).nth(4).click()
    await page.waitForTimeout(120)
    await links(page).nth(2).click()
    await settle(page)
    await expectLanded(page, 'cat-cs-CV')
    await expectCurrent(page, 2)
    // 前一次点击的收尾（最多 1.5 秒后）不会把高亮改回去
    await page.waitForTimeout(1600)
    await expectCurrent(page, 2)
  })
})
