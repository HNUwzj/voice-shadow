<script setup lang="ts">
import { computed, ref } from 'vue'
import { fetchDailyReport, resetHistory, sendChat, uploadImage } from './api'

type Msg = {
  role: 'user' | 'assistant'
  type: 'text' | 'image'
  text?: string
  imageUrl?: string
}

const childId = ref('default-child')
const input = ref('')
const uploadText = ref('')
const messages = ref<Msg[]>([
  { role: 'assistant', type: 'text', text: '宝贝，我在呢。今天最想和我分享什么？' }
])
const defaultMessage: Msg = { role: 'assistant', type: 'text', text: '宝贝，我在呢。今天最想和我分享什么？' }

const loading = ref(false)
const sceneUrl = ref('')
const sceneFallback = ref('radial-gradient(circle at 20% 10%, #264b7a 0%, #1f2f4e 36%, #4a2f26 100%)')
const report = ref<any>(null)
const selectedFile = ref<File | null>(null)

const sceneStyle = computed(() => {
  const overlay = 'linear-gradient(130deg, rgba(7,25,44,.26), rgba(12,60,54,.22), rgba(96,44,22,.18))'
  return {
    backgroundImage: sceneUrl.value ? `${overlay}, url(${sceneUrl.value})` : `${overlay}, ${sceneFallback.value}`
  }
})

function extractSeenObject(text: string): string {
  const cn = text.match(/(?:看见|看到|见到|遇到|发现)(?:了)?(.{1,12}?)(?:[，。！？!?,]|$)/)
  if (cn?.[1]) {
    return cn[1].replace(/^(一只|一条|一头|一个|一位|一群)/, '').trim()
  }
  const en = text.match(/(?:i\s+saw|i\s+met|i\s+found)\s+([a-zA-Z\s]{1,20})(?:[\.,!?]|$)/i)
  if (en?.[1]) {
    return en[1].replace(/^(a|an|the)\s+/i, '').trim()
  }
  return ''
}

function buildFallbackTint(seedText: string): string {
  const seed = Math.abs([...seedText].reduce((n, c) => n + c.charCodeAt(0), 0)) % 360
  const c1 = `hsl(${seed}, 48%, 26%)`
  const c2 = `hsl(${(seed + 50) % 360}, 42%, 22%)`
  const c3 = `hsl(${(seed + 120) % 360}, 38%, 20%)`
  return `radial-gradient(circle at 16% 12%, ${c1} 0%, ${c2} 42%, ${c3} 100%)`
}

async function applyScene(nextBaseUrl: string, sourceText: string) {
  const nonce = Date.now()
  const nextUrl = nextBaseUrl.includes('?') ? `${nextBaseUrl}&v=${nonce}` : `${nextBaseUrl}?v=${nonce}`
  sceneFallback.value = buildFallbackTint(sourceText)

  await new Promise<void>((resolve) => {
    const img = new Image()
    img.onload = () => {
      sceneUrl.value = nextUrl
      resolve()
    }
    img.onerror = () => {
      sceneUrl.value = ''
      resolve()
    }
    img.src = nextUrl
  })
}

async function onSend() {
  const text = input.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', type: 'text', text })
  input.value = ''
  loading.value = true

  try {
    const data = await sendChat({
      child_id: childId.value,
      message: text,
      enable_scene: true,
      enable_psych_analysis: true
    })
    messages.value.push({ role: 'assistant', type: 'text', text: data.reply })
    if (data.scene_image_url) {
      await applyScene(data.scene_image_url, text)
    }
  } catch (err) {
    messages.value.push({ role: 'assistant', type: 'text', text: '我刚刚有点卡住了，咱们再试一次。' })
  } finally {
    loading.value = false
  }
}

function onPickFile(e: Event) {
  const target = e.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

async function onUploadPraise() {
  if (!selectedFile.value || loading.value) return
  loading.value = true
  const caption = uploadText.value.trim()

  const previewUrl = URL.createObjectURL(selectedFile.value)
  messages.value.push({
    role: 'user',
    type: 'image',
    imageUrl: previewUrl,
    text: caption
  })

  // Restore input to placeholder after send.
  uploadText.value = ''

  try {
    const data = await uploadImage(childId.value, caption, selectedFile.value)
    messages.value.push({ role: 'assistant', type: 'text', text: data.reply })
    if (data.scene_image_url && extractSeenObject(caption)) {
      await applyScene(data.scene_image_url, caption)
    }
  } catch {
    messages.value.push({ role: 'assistant', type: 'text', text: '我还没看到图片，能再发一次吗？' })
  } finally {
    selectedFile.value = null
    loading.value = false
  }
}

async function onLoadReport() {
  loading.value = true
  try {
    report.value = await fetchDailyReport(childId.value)
  } finally {
    loading.value = false
  }
}

async function onResetHistory() {
  if (loading.value) return
  if (!window.confirm('确认清空全部历史记录并重置日报吗？')) return

  loading.value = true
  try {
    await resetHistory()
    messages.value = [defaultMessage]
    report.value = null
    input.value = ''
    uploadText.value = ''
    selectedFile.value = null
    sceneUrl.value = ''
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="app" :style="sceneStyle">
    <header class="hero">
      <h1>声影随行 · 双向陪伴助手</h1>
    </header>

    <main class="layout">
      <section class="chat-card glass">
        <div class="messages">
          <article v-for="(m, idx) in messages" :key="idx" class="bubble" :class="m.role">
            <template v-if="m.type === 'image'">
              <img v-if="m.imageUrl" :src="m.imageUrl" alt="上传的图片" class="bubble-image" />
              <p v-if="m.text" class="bubble-caption">{{ m.text }}</p>
            </template>
            <template v-else>
              {{ m.text }}
            </template>
          </article>
        </div>

        <div class="composer">
          <input v-model="input" placeholder="和爸爸妈妈说说今天发生了什么..." @keyup.enter="onSend" />
          <button @click="onSend" :disabled="loading">发送</button>
        </div>

        <div class="uploader">
          <input v-model="uploadText" placeholder="和爸爸妈妈分享一下今天做了什么吧" />
          <input type="file" accept="image/*" @change="onPickFile" />
          <button @click="onUploadPraise" :disabled="loading || !selectedFile">随手拍夸夸</button>
        </div>

        <div class="chat-footer-actions">
          <button class="danger" @click="onResetHistory" :disabled="loading">删除历史记录</button>
        </div>
      </section>

      <aside class="radar-card glass">
        <h2>父母端心理日报</h2>
        <button @click="onLoadReport" :disabled="loading">刷新日报</button>

        <div v-if="report" class="report">
          <p>日期：{{ report.date }}</p>
          <p>消息数：{{ report.total_messages }}</p>
          <p>自卑风险均值：{{ report.risk_summary.self_esteem_risk_avg }}</p>
          <p>被欺凌风险均值：{{ report.risk_summary.bullying_risk_avg }}</p>
          <p>孤独风险均值：{{ report.risk_summary.loneliness_risk_avg }}</p>
          <p>陪伴需求均值：{{ report.risk_summary.companionship_need_avg }}</p>
          <p class="suggestion">建议：{{ report.suggestion }}</p>
          <ul>
            <li v-for="(item, i) in report.highlights" :key="i">{{ item }}</li>
          </ul>
        </div>
      </aside>
    </main>
  </div>
</template>
