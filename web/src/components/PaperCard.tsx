// 一篇论文的卡片
import { useState } from 'preact/hooks'
import { isSaved, prefs, toggleSaved } from '../lib/store'
import type { PaperView } from '../lib/view'
import { Icon } from './Icon'
import { Rich } from './Rich'

const LINK = 'inline-flex items-center gap-0.5 text-muted-foreground underline decoration-foreground/30 underline-offset-[3px] hover:text-foreground hover:decoration-current'

export function PaperCard({ paper, date }: { paper: PaperView; date: string }) {
  const abs = prefs.value.abs
  const [open, setOpen] = useState(false)
  const [authorsOpen, setAuthorsOpen] = useState(false)
  const starred = isSaved(paper.id)
  const showEn = (abs === 'both' || abs === 'en' || (abs === 'none' && open)) && paper.abstract
  const showZh = (abs === 'both' || abs === 'zh' || (abs === 'none' && open)) && paper.abstractZh

  return (
    <article class="rounded-xl border border-border bg-card px-[22px] pb-3.5 pt-[18px] max-[760px]:px-4 max-[760px]:pb-3 max-[760px]:pt-[15px]" data-id={paper.id}>
      {paper.kind === 'cross' && (
        <div class="mb-2 flex flex-wrap gap-1.5">
          <span class="inline-flex h-[22px] items-center rounded-full border border-border px-[9px] text-xs text-muted-foreground">cross-list</span>
          <span class="inline-flex h-[22px] items-center rounded-full border border-border px-[9px] font-mono text-xs text-muted-foreground">{paper.primary}</span>
        </div>
      )}
      <h3 class="m-0 text-lg font-semibold">
        <a href={paper.arxivUrl} target="_blank" rel="noopener" class="hover:underline hover:decoration-1 hover:underline-offset-4">
          <Rich text={paper.title} links={false} />
        </a>
      </h3>
      {paper.titleZh && (
        <p class="mt-[3px] text-muted-foreground">
          <Rich text={paper.titleZh} links={false} />
        </p>
      )}
      <p class="mt-2 flex items-baseline gap-3 text-sm text-faint">
        <span class="flex-none font-mono text-xs">{paper.id}</span>
        {paper.authors && (
          <span class={`min-w-0 cursor-default ${authorsOpen ? '' : 'line-clamp-2'}`} onClick={() => setAuthorsOpen(!authorsOpen)}>
            {paper.authors}
          </span>
        )}
      </p>
      {paper.comments && (
        <p class="mt-1 break-words text-sm text-faint">
          <Rich text={paper.comments} />
        </p>
      )}
      {(showEn || showZh) && (
        <div class="mt-3 border-t border-border pt-3 leading-7">
          {showEn && (
            <p>
              <Rich text={paper.abstract} />
            </p>
          )}
          {showZh && (
            <p class={`text-muted-foreground ${showEn ? 'mt-2.5' : ''}`}>
              <Rich text={paper.abstractZh} />
            </p>
          )}
        </div>
      )}
      <div class="mt-3.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
        {abs === 'none' && (paper.abstract || paper.abstractZh) && (
          <button type="button" class="inline-flex items-center gap-1 text-muted-foreground" onClick={() => setOpen(!open)}>
            摘要
            <Icon name="down" class={`size-3.5 transition-transform ${open ? 'rotate-180' : ''}`} />
          </button>
        )}
        <a class={LINK} href={paper.arxivUrl} target="_blank" rel="noopener">
          arXiv
          <Icon name="out" class="size-[13px]" />
        </a>
        <a class={LINK} href={paper.pdfUrl} target="_blank" rel="noopener">
          PDF
          <Icon name="out" class="size-[13px]" />
        </a>
        <a class={LINK} href={paper.htmlUrl} target="_blank" rel="noopener">
          HTML
          <Icon name="out" class="size-[13px]" />
        </a>
        {paper.hjfyUrl && (
          <a class={LINK} href={paper.hjfyUrl} target="_blank" rel="noopener">
            幻觉翻译
            <Icon name="out" class="size-[13px]" />
          </a>
        )}
        <button
          type="button"
          aria-label="收藏"
          aria-pressed={starred}
          onClick={() => toggleSaved({ id: paper.id, title: paper.title, date })}
          class={`ml-auto inline-grid size-[34px] place-items-center rounded-lg border ${
            starred ? 'border-foreground bg-foreground text-background' : 'border-border bg-card hover:bg-secondary'
          }`}
        >
          <Icon name="star" filled={starred} />
        </button>
      </div>
    </article>
  )
}
