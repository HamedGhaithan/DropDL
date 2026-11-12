// Shared palette for the main window, editor and detached player (2.1).
export const DARK_ACCENTS = {aurora:'#6aa6ff',emerald:'#4fd8ac',violet:'#a993ff',blue:'#5fb3ff',rose:'#f58fb1',amber:'#f2bd5c'}
export const LIGHT_ACCENTS = {aurora:'#2563eb',emerald:'#047857',violet:'#6d4bd3',blue:'#0b6bcb',rose:'#be2f62',amber:'#94600b'}
export type AccentName = keyof typeof DARK_ACCENTS
export const DEFAULT_ACCENT: AccentName = 'aurora'
export function accentColor(theme: string | undefined, name: string | null): string {
  const palette: Record<string, string> = theme === 'light' ? LIGHT_ACCENTS : DARK_ACCENTS
  return palette[name || DEFAULT_ACCENT] || palette[DEFAULT_ACCENT]
}
