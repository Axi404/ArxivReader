import { fontFamily } from 'tailwindcss/defaultTheme'

// 颜色、圆角、字体都照博客（axi404.top）的 tailwind 配置；字号用 tailwind 默认的那几级，
// 正好就是博客用的 12 / 14 / 16 / 18 / 20 / 24 / 30
const hsl = (name) => `hsl(var(--${name}) / <alpha-value>)`

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{astro,ts,tsx}'],
  darkMode: ['class'],
  theme: {
    extend: {
      colors: {
        border: hsl('border'),
        background: hsl('background'),
        foreground: hsl('foreground'),
        card: hsl('card'),
        secondary: hsl('secondary'),
        muted: { DEFAULT: hsl('muted'), foreground: hsl('muted-foreground') },
        faint: hsl('faint'),
        danger: hsl('danger')
      },
      borderRadius: { xl: '12px', '2xl': '16px', '3xl': '18px' },
      fontFamily: {
        sans: ['Century Gothic', '-apple-system', 'BlinkMacSystemFont', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', ...fontFamily.sans],
        mono: fontFamily.mono
      }
    }
  }
}
