// Mirrors backend/spectra/formats.py so the UI can tell whether a plugin applies to a format.
const IMAGE = ['png', 'jpeg', 'bmp', 'tiff', 'gif', 'webp', 'ico', 'heic']
const AUDIO = ['wav', 'mp3', 'flac', 'ogg', 'opus', 'aac', 'm4a', 'aiff']
const VIDEO = ['mp4', 'mkv', 'avi', 'mov', 'webm', 'mpeg']

export function categoryOf(fmt: string): 'image' | 'audio' | 'video' | null {
  if (IMAGE.includes(fmt)) return 'image'
  if (AUDIO.includes(fmt)) return 'audio'
  if (VIDEO.includes(fmt)) return 'video'
  return null
}

/** Does any declared token cover this evidence format? `fmt === null` means "not identified yet". */
export function supportsFormat(tokens: string[], fmt: string | null): boolean {
  return tokens.some((t) => {
    if (t === '*') return true
    if (fmt === null) return false
    if (t === fmt) return true
    return t.endsWith(':*') && categoryOf(fmt) === t.slice(0, -2)
  })
}
