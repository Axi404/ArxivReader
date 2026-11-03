import { toastText } from '../lib/store'

export function Toast() {
  return (
    <div
      role="status"
      class={`pointer-events-none fixed bottom-7 left-1/2 z-[99] -translate-x-1/2 rounded-lg bg-foreground px-4 py-2 text-sm text-background transition-opacity duration-200 ${
        toastText.value ? 'opacity-95' : 'opacity-0'
      }`}
    >
      {toastText.value}
    </div>
  )
}
