export type ChatPayload = {
  child_id: string
  message: string
  enable_scene: boolean
  enable_psych_analysis: boolean
}

export type PraiseImageResponse = {
  reply: string
  image_url?: string | null
  scene_image_url?: string | null
  details: Record<string, unknown>
}

const API_BASE = 'http://127.0.0.1:8001'

export async function sendChat(payload: ChatPayload) {
  const res = await fetch(`${API_BASE}/api/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
  if (!res.ok) throw new Error('聊天接口失败')
  return res.json()
}

export async function fetchDailyReport(childId: string) {
  const res = await fetch(`${API_BASE}/api/report/daily?child_id=${encodeURIComponent(childId)}`)
  if (!res.ok) throw new Error('日报接口失败')
  return res.json()
}

export async function uploadImage(childId: string, text: string, file: File): Promise<PraiseImageResponse> {
  const formData = new FormData()
  formData.append('child_id', childId)
  formData.append('text', text)
  formData.append('image', file)

  const res = await fetch(`${API_BASE}/api/praise-image`, {
    method: 'POST',
    body: formData
  })
  if (!res.ok) throw new Error('图片夸夸接口失败')
  return res.json()
}

export async function resetHistory() {
  const res = await fetch(`${API_BASE}/api/history/reset`, {
    method: 'POST'
  })
  if (!res.ok) throw new Error('清空历史接口失败')
  return res.json()
}
