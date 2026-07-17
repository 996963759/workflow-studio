export type MessageBlock =
  | { type: 'text'; content: string }
  | { type: 'audio' | 'image'; url: string; label: string }

const MEDIA_URL_PATTERN = /https?:\/\/[^\s<>"']+/gi
const AUDIO_EXTENSION_PATTERN = /\.(mp3|wav|m4a|aac|ogg|flac)(?:$|\?)/i
const IMAGE_EXTENSION_PATTERN = /\.(png|jpe?g|webp|gif|avif|bmp)(?:$|\?)/i
const MEDIA_LABEL_PATTERN = /(音频地址|音频|图片\s*\d*|配图\s*\d*)\s*[：:]\s*$/

const trimUrlPunctuation = (value: string) => value.replace(/[，。；;！？!?)）]+$/, '')

export const parseMessageBlocks = (content: string): MessageBlock[] => {
  const blocks: MessageBlock[] = []
  let textBuffer = ''

  const flushText = () => {
    const text = textBuffer.trim()
    if (text) blocks.push({ type: 'text', content: text })
    textBuffer = ''
  }

  content.split('\n').forEach((line, lineIndex, lines) => {
    const matches = Array.from(line.matchAll(MEDIA_URL_PATTERN))
    const mediaMatches = matches.filter((match) => {
      const url = trimUrlPunctuation(match[0])
      const prefix = line.slice(0, match.index ?? 0)
      return AUDIO_EXTENSION_PATTERN.test(url) || IMAGE_EXTENSION_PATTERN.test(url) || MEDIA_LABEL_PATTERN.test(prefix)
    })

    if (mediaMatches.length === 0) {
      textBuffer += line
      if (lineIndex < lines.length - 1) textBuffer += '\n'
      return
    }

    let cursor = 0
    mediaMatches.forEach((match, mediaIndex) => {
      const rawUrl = match[0]
      const url = trimUrlPunctuation(rawUrl)
      const prefix = line.slice(cursor, match.index ?? 0)
      const labelMatch = prefix.match(MEDIA_LABEL_PATTERN)
      textBuffer += labelMatch ? prefix.slice(0, labelMatch.index) : prefix
      flushText()

      const label = labelMatch?.[1]?.replace(/\s+/g, ' ') ?? ''
      const type = AUDIO_EXTENSION_PATTERN.test(url) || label.includes('音频') ? 'audio' : 'image'
      blocks.push({
        type,
        url,
        label: label || (type === 'audio' ? '生成音频' : `生成图片 ${mediaIndex + 1}`),
      })
      cursor = (match.index ?? 0) + rawUrl.length
    })

    textBuffer += line.slice(cursor)
    if (lineIndex < lines.length - 1) textBuffer += '\n'
  })

  flushText()
  return blocks
}
