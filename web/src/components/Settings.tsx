// 设置：每日页有范围、摘要；首页有归档每页几天；两边都有主题
import type { ComponentChildren } from 'preact'
import { PAGE_SIZES, prefs, setPref, type AbsMode, type Mode, type Scope } from '../lib/store'
import { Seg } from './ui'

function Field({ label, children }: { label: string; children: ComponentChildren }) {
  return (
    <div class="grid grid-cols-[44px_auto] items-center gap-2.5 text-sm [&+&]:mt-2.5">
      <span class="text-muted-foreground">{label}</span>
      {children}
    </div>
  )
}

export function Settings({ daily }: { daily: boolean }) {
  const p = prefs.value
  return (
    <div class="px-4 py-3.5">
      {daily && (
        <>
          <Field label="范围">
            <Seg<Scope> value={p.scope} onChange={(v) => setPref('scope', v)} options={[['primary', '主领域'], ['cross', 'cross-list'], ['all', '全部']]} />
          </Field>
          <Field label="摘要">
            <Seg<AbsMode> value={p.abs} onChange={(v) => setPref('abs', v)} options={[['both', '双语'], ['zh', '中文'], ['en', '英文'], ['none', '不显示']]} />
          </Field>
        </>
      )}
      {!daily && (
        <Field label="每页">
          <Seg<string> value={String(p.pageSize)} onChange={(v) => setPref('pageSize', Number(v))} options={PAGE_SIZES.map((n) => [String(n), String(n)])} />
        </Field>
      )}
      <Field label="主题">
        <Seg<Mode> value={p.mode} onChange={(v) => setPref('mode', v)} options={[['auto', '自动'], ['light', '浅色'], ['dark', '深色']]} />
      </Field>
    </div>
  )
}
