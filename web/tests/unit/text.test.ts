import { describe, expect, it } from 'vitest'
import { detex, segments } from '../../src/lib/text'

describe('detex', () => {
  it('drops common TeX wrappers and escapes', () => {
    expect(detex('a \\emph{diffusion} b \\textbf{x} 50\\% \\& \\_')).toBe('a diffusion b x 50% & _')
  })
  it('turns ties into non-breaking spaces but keeps lone tildes', () => {
    expect(detex('Fig.~3')).toBe('Fig.\u00a03')
    expect(detex('about ~5 ms')).toBe('about ~5 ms')
  })
})

describe('segments', () => {
  it('links URLs without their trailing punctuation', () => {
    expect(segments('Code: https://example.com/code. More (see https://a.org/x).')).toEqual([
      { text: 'Code: ' },
      { text: 'https://example.com/code', href: 'https://example.com/code' },
      { text: '. More (see ' },
      { text: 'https://a.org/x', href: 'https://a.org/x' },
      { text: ').' }
    ])
  })
  it('returns plain text unchanged', () => {
    expect(segments('no links here')).toEqual([{ text: 'no links here' }])
    expect(segments('')).toEqual([])
  })
})
