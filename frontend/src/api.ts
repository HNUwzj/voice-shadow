export type ChatPayload = {
  child_id: string
  message: string
  enable_scene: boolean
  enable_psych_analysis: boolean
  voice_id?: string | null
}

export type PraiseImageResponse = {
  reply: string
  image_url?: string | null
  scene_image_url?: string | null
  assistant_audio_url?: string | null
  details: Record<string, unknown>
}

export type ChatResponse = {
  reply: string
  scene_image_url?: string | null
  assistant_audio_url?: string | null
  timestamp: string
}

export type ParentStyleResponse = {
  child_id: string
  use_default: boolean
  custom_rules: string
  default_rules: string
  active_rules: string
}

export type VoiceEnrollResponse = {
  voice_id: string
  status: string
  sample_audio_url: string
  request_id?: string | null
}

export type VoiceSynthesizeResponse = {
  voice_id: string
  audio_url: string
  request_id?: string | null
}

export type VoiceItem = {
  child_id: string
  voice_id: string
  status: string
  display_name: string
  prefix?: string | null
  sample_audio_url?: string | null
  timestamp: string
}

export type VoiceListResponse = {
  child_id: string
  items: VoiceItem[]
}

export type ConversationItem = {
  child_id: string
  role: string
  content: string
  message_type: string
  image_url?: string | null
  audio_url?: string | null
  timestamp: string
}

export type ConversationListResponse = {
  child_id: string
  day: string
  items: ConversationItem[]
}

export type MailboxItem = {
  child_id: string
  sender: string
  content: string
  message_type: 'text' | 'audio'
  audio_url?: string | null
  timestamp: string
}

export type MailboxListResponse = {
  child_id: string
  items: MailboxItem[]
}

const API_BASE = 'http://127.0.0.1:8001'

async function readErrorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const data = await res.json()
    const detail = (data as { detail?: unknown })?.detail
    if (typeof detail === 'string' && detail.trim()) return detail
    if (Array.isArray(detail) && detail.length) return String(detail[0])
  } catch {
    // Keep fallback when the backend does not return JSON.
  }
  return fallback
}

export async function sendChat(payload: ChatPayload): Promise<ChatResponse> {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '聊天接口失败'))
  return res.json()
}

export async function fetchParentStyle(childId: string): Promise<ParentStyleResponse> {
  const res = await fetch(`${API_BASE}/api/parent-style?child_id=${encodeURIComponent(childId)}`)
  if (!res.ok) throw new Error(await readErrorMessage(res, '获取家长设定失败'))
  return res.json()
}

export async function saveParentStyle(
  childId: string,
  useDefault: boolean,
  customRules: string
): Promise<ParentStyleResponse> {
  const res = await fetch(`${API_BASE}/api/parent-style`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      child_id: childId,
      use_default: useDefault,
      custom_rules: customRules
    })
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '保存家长设定失败'))
  return res.json()
}

export async function fetchDailyReport(childId: string) {
  const res = await fetch(`${API_BASE}/api/report/daily?child_id=${encodeURIComponent(childId)}`)
  if (!res.ok) throw new Error(await readErrorMessage(res, '日报接口失败'))
  return res.json()
}

export async function uploadImage(
  childId: string,
  text: string,
  file: File,
  voiceId?: string | null
): Promise<PraiseImageResponse> {
  const formData = new FormData()
  formData.append('child_id', childId)
  formData.append('text', text)
  if (voiceId) formData.append('voice_id', voiceId)
  formData.append('image', file)

  const res = await fetch(`${API_BASE}/api/praise-image`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '图片上传接口失败'))
  return res.json()
}

export async function fetchMailbox(childId: string, viewer?: string): Promise<MailboxListResponse> {
  const params = new URLSearchParams({ child_id: childId })
  if (viewer) params.set('viewer', viewer)
  const res = await fetch(`${API_BASE}/api/mailbox?${params.toString()}`)
  if (!res.ok) throw new Error(await readErrorMessage(res, '获取留言失败'))
  return res.json()
}

export async function clearMailbox(childId: string, viewer: string): Promise<void> {
  const formData = new FormData()
  formData.append('child_id', childId)
  formData.append('viewer', viewer)

  const res = await fetch(`${API_BASE}/api/mailbox/clear`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '清空留言失败'))
}

export async function sendMailboxItem(
  childId: string,
  sender: string,
  text: string,
  audio?: File | null
): Promise<MailboxItem> {
  const formData = new FormData()
  formData.append('child_id', childId)
  formData.append('sender', sender)
  formData.append('text', text)
  if (audio) formData.append('audio', audio)

  const res = await fetch(`${API_BASE}/api/mailbox`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '发送留言失败'))
  return res.json()
}

export async function resetHistory() {
  const res = await fetch(`${API_BASE}/api/history/reset`, { method: 'POST' })
  if (!res.ok) throw new Error(await readErrorMessage(res, '清空历史接口失败'))
  return res.json()
}

export async function enrollVoice(childId: string, file: File, prefix = ''): Promise<VoiceEnrollResponse> {
  const formData = new FormData()
  formData.append('child_id', childId)
  if (prefix.trim()) formData.append('prefix', prefix.trim())
  formData.append('audio', file)

  const res = await fetch(`${API_BASE}/api/voice/enroll`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '人声注册失败'))
  return res.json()
}

export async function synthesizeVoice(childId: string, text: string, voiceId?: string): Promise<VoiceSynthesizeResponse> {
  const res = await fetch(`${API_BASE}/api/voice/synthesize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ child_id: childId, text, voice_id: voiceId ?? null })
  })
  if (!res.ok) throw new Error(await readErrorMessage(res, '语音合成失败'))
  return res.json()
}

export async function fetchVoices(childId: string): Promise<VoiceListResponse> {
  const res = await fetch(`${API_BASE}/api/voice/list?child_id=${encodeURIComponent(childId)}`)
  if (!res.ok) throw new Error(await readErrorMessage(res, '获取人声列表失败'))
  return res.json()
}

export async function deleteVoice(childId: string, voiceId: string): Promise<void> {
  const res = await fetch(
    `${API_BASE}/api/voice/${encodeURIComponent(voiceId)}?child_id=${encodeURIComponent(childId)}`,
    { method: 'DELETE' }
  )
  if (!res.ok) throw new Error(await readErrorMessage(res, '删除人声失败'))
}

export async function fetchTodayConversations(childId: string): Promise<ConversationListResponse> {
  const res = await fetch(`${API_BASE}/api/conversations/today?child_id=${encodeURIComponent(childId)}`)
  if (!res.ok) throw new Error(await readErrorMessage(res, '获取当天聊天记录失败'))
  return res.json()
}
