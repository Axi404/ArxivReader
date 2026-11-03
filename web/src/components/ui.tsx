// 几个小控件：方形图标按钮、普通按钮、分段按钮
import type { ButtonHTMLAttributes, ComponentChildren } from 'preact'
import { Icon, type IconName } from './Icon'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }

export function IconButton({ icon, label, active, class: cls = '', children, ...rest }: ButtonProps & { icon: IconName; label: string }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      class={`relative inline-grid size-[34px] place-items-center rounded-lg border transition-colors ${
        active ? 'border-foreground bg-foreground text-background' : 'border-border bg-card text-foreground hover:bg-secondary'
      } ${cls}`}
      {...rest}
    >
      <Icon name={icon} />
      {children}
    </button>
  )
}

export function Button({ dark, danger, class: cls = '', children, ...rest }: ButtonProps & { dark?: boolean; danger?: boolean }) {
  const tone = dark
    ? 'border-foreground bg-foreground text-background hover:opacity-90'
    : 'border-border bg-secondary hover:border-foreground/35 hover:bg-muted'
  return (
    <button
      type="button"
      class={`inline-flex h-[34px] items-center gap-1.5 whitespace-nowrap rounded-lg border px-3.5 text-sm transition-colors ${tone} ${
        danger ? 'text-danger' : ''
      } ${cls}`}
      {...rest}
    >
      {children}
    </button>
  )
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div class="inline-flex justify-self-start overflow-hidden rounded-lg border border-border bg-card">
      {options.map(([v, label]) => (
        <button
          key={v}
          type="button"
          class={`whitespace-nowrap border-r border-border px-3 py-[5px] text-sm last:border-r-0 ${
            v === value ? 'bg-foreground text-background' : 'hover:bg-secondary'
          }`}
          onClick={() => onChange(v)}
        >
          {label}
        </button>
      ))}
    </div>
  )
}

export function Card({ class: cls = '', children }: { class?: string; children: ComponentChildren }) {
  return <div class={`rounded-xl border border-border bg-card ${cls}`}>{children}</div>
}
