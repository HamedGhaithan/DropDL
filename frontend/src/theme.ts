// Shared palette for the main window, editor and detached player.
// 3.0 "Flare" identity: Ultraviolet is the signature accent; Flare is the brand's coral. Keys stay stable so saved
// preferences keep working (the old default, Aurora, is moved to Ultraviolet once; see migrateAccent).
export const DARK_ACCENTS = {violet:'#8466ff',flare:'#ff7262',aurora:'#62a8ff',emerald:'#34d399',rose:'#ff6fae',amber:'#ffbe4d',blue:'#4fa3ff'}
export const LIGHT_ACCENTS = {violet:'#5b3df0',flare:'#d63e26',aurora:'#2563eb',emerald:'#047857',rose:'#c0265f',amber:'#946000',blue:'#0a62c9'}
export type AccentName = keyof typeof DARK_ACCENTS
export const DEFAULT_ACCENT: AccentName = 'violet'
const ACCENT_VERSION = 'flare-3'

/** Run once per window: people still on the 2.x default accent get the 3.0 signature colour. */
export function migrateAccent() {
  try {
    if (localStorage.getItem('dropdl-accent-version') === ACCENT_VERSION) return
    if (!localStorage.getItem('dropdl-accent') || localStorage.getItem('dropdl-accent') === 'aurora') localStorage.setItem('dropdl-accent', DEFAULT_ACCENT)
    localStorage.setItem('dropdl-accent-version', ACCENT_VERSION)
  } catch { /* storage unavailable: the default applies */ }
}

export function accentColor(theme: string | undefined, name: string | null): string {
  const palette: Record<string, string> = theme === 'light' ? LIGHT_ACCENTS : DARK_ACCENTS
  return palette[name || DEFAULT_ACCENT] || palette[DEFAULT_ACCENT]
}

/** Text colour on an accent fill: white unless the accent is light (amber, emerald in dark mode). */
export function onAccent(color: string): string {
  const hex = color.replace('#', ''), channel = (i: number) => {const v = parseInt(hex.slice(i, i + 2), 16) / 255; return v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4}
  const luminance = .2126 * channel(0) + .7152 * channel(2) + .0722 * channel(4)
  return luminance > .36 ? '#120d1f' : '#ffffff'
}

/** Apply the accent (and its readable text colour) to the document. */
export function applyAccent(theme: string | undefined, name: string | null) {
  const color = accentColor(theme, name)
  document.documentElement.style.setProperty('--accent', color)
  document.documentElement.style.setProperty('--on-accent', onAccent(color))
}
