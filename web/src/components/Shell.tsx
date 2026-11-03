// 两个页面共用的外壳：顶栏、收藏抽屉、提示、页脚；主题和访问计数也在这里
import type { ComponentChildren } from 'preact'
import { useEffect, useState } from 'preact/hooks'
import { recordVisit } from '../lib/api'
import { applyTheme, initStores, syncSavedAcrossTabs } from '../lib/store'
import { Header } from './Header'
import { SavedDrawer } from './SavedDrawer'
import { Toast } from './Toast'

export function Shell({ daily, children }: { daily: boolean; children: ComponentChildren }) {
  const [savedOpen, setSavedOpen] = useState(false)

  useEffect(() => {
    initStores()
    const stopTheme = applyTheme()
    const stopSync = syncSavedAcrossTabs()
    recordVisit()
    return () => {
      stopTheme()
      stopSync()
    }
  }, [])

  return (
    <>
      <Header daily={daily} onOpenSaved={() => setSavedOpen(true)} />
      <main class="pb-[120px] pt-5">
        <div class="mx-auto max-w-[824px] px-8 max-[760px]:px-4">
          {children}
          <footer class="mt-[60px] flex gap-[18px] border-t border-border pb-10 pt-[18px] text-sm text-muted-foreground">
            <span>© 2026 阿汐</span>
          </footer>
        </div>
      </main>
      <SavedDrawer open={savedOpen} onClose={() => setSavedOpen(false)} />
      <Toast />
    </>
  )
}
