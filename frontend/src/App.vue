<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import {
  clearMailbox,
  deleteVoice,
  enrollVoice,
  fetchDailyReport,
  fetchMailbox,
  fetchParentStyle,
  fetchTodayConversations,
  fetchVoices,
  resetHistory,
  sendChat,
  sendMailboxItem,
  saveParentStyle,
  uploadImage,
  type ConversationItem,
  type MailboxItem,
  type VoiceItem
} from './api'

type PageKey = 'child' | 'parent'
type ConfirmAction = 'reset-history' | 'clear-mailbox' | ''

type Msg = {
  role: 'user' | 'assistant'
  type: 'text' | 'image'
  text?: string
  imageUrl?: string
  audioUrl?: string
}

type DailyReport = {
  child_id: string
  date: string
  total_messages: number
  risk_summary?: Record<string, number>
  suggestion?: string
  highlights?: string[]
}

const childId = ref('default-child')
const activePage = ref<PageKey>('child')
const input = ref('')
const loading = ref(false)
const sceneUrl = ref('')
const sceneFallback = ref('radial-gradient(circle at 24% 18%, #266d64 0%, #213d42 44%, #5b3140 100%)')
const report = ref<DailyReport | null>(null)
const selectedFile = ref<File | null>(null)
const voiceFile = ref<File | null>(null)
const voicePrefix = ref('')
const selectedVoiceId = ref('')
const recording = ref(false)
const recorder = ref<MediaRecorder | null>(null)
const recordingStream = ref<MediaStream | null>(null)
const recordedChunks = ref<Blob[]>([])
const voiceModalOpen = ref(false)
const registeredVoices = ref<VoiceItem[]>([])
const deletingVoiceId = ref('')
const messagesRef = ref<HTMLElement | null>(null)
const mailboxRef = ref<HTMLElement | null>(null)
const mailboxItems = ref<MailboxItem[]>([])
const mailboxText = ref('')
const mailboxAudioFile = ref<File | null>(null)
const mailboxRecording = ref(false)
const mailboxRecorder = ref<MediaRecorder | null>(null)
const mailboxStream = ref<MediaStream | null>(null)
const mailboxChunks = ref<Blob[]>([])
const confirmModalOpen = ref(false)
const confirmTitle = ref('')
const confirmMessage = ref('')
const confirmAction = ref<ConfirmAction>('')
const confirmLoading = ref(false)
const parentStyleUseDefault = ref(true)
const parentStyleCustomRules = ref('')
const parentStyleDefaultRules = ref('')
const parentStyleSaving = ref(false)
let mailboxPollTimer: number | undefined
let reportPollTimer: number | undefined
let voicePollTimer: number | undefined

const defaultMessage: Msg = {
  role: 'assistant',
  type: 'text',
  text: '宝贝，爸爸妈妈在这里。今天最想先跟我们说哪件小事？'
}
const messages = ref<Msg[]>([defaultMessage])
const unavailableAudioUrls = ref<Set<string>>(new Set())

const selectedVoiceName = computed(() => {
  const matched = registeredVoices.value.find((voice) => voice.voice_id === selectedVoiceId.value)
  return matched?.display_name || '暂不使用人声'
})

const mailboxSender = computed(() => (activePage.value === 'parent' ? 'parent' : 'child'))
const playingAudioKey = ref('')
let activeAudio: HTMLAudioElement | null = null

const riskItems = computed(() => {
  const risk = report.value?.risk_summary ?? {}
  return [
    ['自卑风险', risk.self_esteem_risk_avg],
    ['被欺负风险', risk.bullying_risk_avg],
    ['孤独风险', risk.loneliness_risk_avg],
    ['陪伴需求', risk.companionship_need_avg]
  ].map(([label, value]) => ({
    label: String(label),
    value: typeof value === 'number' ? value.toFixed(2) : '-'
  }))
})

const sceneStyle = computed(() => {
  const overlay = 'linear-gradient(130deg, rgba(16, 28, 34, .34), rgba(20, 76, 69, .24), rgba(136, 57, 62, .20))'
  return {
    backgroundImage: sceneUrl.value ? `${overlay}, url(${sceneUrl.value})` : `${overlay}, ${sceneFallback.value}`
  }
})

function resolvePageFromLocation(): PageKey {
  if (window.location.port === '5174') return 'parent'
  if (window.location.port === '5173') return 'child'
  if (window.location.pathname.endsWith('/parent') || window.location.hash === '#parent') return 'parent'
  return 'child'
}

function scrollMessagesToBottom(behavior: ScrollBehavior = 'smooth') {
  const el = messagesRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
}

function scrollMailboxToBottom(behavior: ScrollBehavior = 'smooth') {
  const el = mailboxRef.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior })
}

function toAssetUrl(relativeUrl?: string | null): string | undefined {
  if (!relativeUrl) return undefined
  if (relativeUrl.startsWith('http://') || relativeUrl.startsWith('https://') || relativeUrl.startsWith('blob:')) {
    return relativeUrl
  }
  const base = 'http://127.0.0.1:8001'
  return `${base}${relativeUrl}${relativeUrl.includes('?') ? '&' : '?'}v=${Date.now()}`
}

function playAudioUrl(url?: string | null) {
  const src = toAssetUrl(url)
  if (!src) return

  activeAudio?.pause()
  activeAudio = new Audio(src)
  activeAudio.onended = () => {
    activeAudio = null
  }
  activeAudio.onerror = () => {
    activeAudio = null
    markAudioUnavailable(src)
  }
  void activeAudio.play().catch(() => {
    activeAudio = null
  })
}

function markAudioUnavailable(url?: string | null) {
  if (!url) return
  const next = new Set(unavailableAudioUrls.value)
  next.add(url)
  unavailableAudioUrls.value = next
}

function canShowAudio(url?: string | null) {
  return !!url && !unavailableAudioUrls.value.has(url)
}

function playCompactAudio(relativeUrl?: string | null) {
  if (!relativeUrl) return

  if (playingAudioKey.value === relativeUrl && activeAudio) {
    activeAudio.pause()
    activeAudio.currentTime = 0
    activeAudio = null
    playingAudioKey.value = ''
    return
  }

  activeAudio?.pause()
  activeAudio = new Audio(toAssetUrl(relativeUrl))
  playingAudioKey.value = relativeUrl
  activeAudio.onended = () => {
    playingAudioKey.value = ''
    activeAudio = null
  }
  activeAudio.onerror = () => {
    playingAudioKey.value = ''
    activeAudio = null
    window.alert('语音播放失败。')
  }
  void activeAudio.play()
}

function mapConversationItemToMsg(item: ConversationItem): Msg | null {
  const role = item.role === 'assistant' ? 'assistant' : 'user'
  const messageType = item.message_type === 'image' ? 'image' : 'text'

  if (messageType === 'image') {
    return {
      role,
      type: 'image',
      text: item.content || '',
      imageUrl: toAssetUrl(item.image_url)
    }
  }

  return {
    role,
    type: 'text',
    text: item.content || '',
    audioUrl: role === 'assistant' ? toAssetUrl(item.audio_url) : undefined
  }
}

function persistSelectedVoice(voiceId: string) {
  selectedVoiceId.value = voiceId
  window.localStorage.setItem(`selectedVoice:${childId.value}`, voiceId)
}

function onSelectVoice(event: Event) {
  const target = event.target as HTMLSelectElement
  persistSelectedVoice(target.value)
}

async function syncVoices() {
  try {
    const data = await fetchVoices(childId.value)
    registeredVoices.value = data.items
    const savedVoiceId = window.localStorage.getItem(`selectedVoice:${childId.value}`) || ''
    const stillExists = data.items.some((voice) => voice.voice_id === savedVoiceId)
    selectedVoiceId.value = stillExists ? savedVoiceId : ''
  } catch {
    selectedVoiceId.value = ''
    registeredVoices.value = []
  }
}

async function syncVoicesSafely() {
  try {
    const data = await fetchVoices(childId.value)
    registeredVoices.value = data.items
    const savedVoiceId = window.localStorage.getItem(`selectedVoice:${childId.value}`) || ''
    const stillExists = data.items.some((voice) => voice.voice_id === savedVoiceId)
    selectedVoiceId.value = stillExists ? savedVoiceId : ''
  } catch {
    // Keep current UI state during polling to avoid flicker on transient errors.
  }
}

async function loadTodayMessages() {
  try {
    const data = await fetchTodayConversations(childId.value)
    const mapped = data.items
      .map((item) => mapConversationItemToMsg(item))
      .filter((item): item is Msg => item !== null)
    messages.value = mapped.length > 0 ? mapped : [defaultMessage]
  } catch {
    messages.value = [defaultMessage]
  }
}

async function loadMailbox() {
  try {
    const data = await fetchMailbox(childId.value, mailboxSender.value)
    mailboxItems.value = data.items
  } catch {
    mailboxItems.value = []
  }
}

async function loadReport() {
  try {
    report.value = await fetchDailyReport(childId.value)
  } catch {
    // Keep the current report on transient backend errors.
  }
}

async function loadParentStyle() {
  try {
    const data = await fetchParentStyle(childId.value)
    parentStyleUseDefault.value = data.use_default
    parentStyleCustomRules.value = data.custom_rules || ''
    parentStyleDefaultRules.value = data.default_rules || ''
  } catch {
    // Keep the editor usable even if this transiently fails.
  }
}

async function onSaveParentStyle() {
  if (parentStyleSaving.value) return
  parentStyleSaving.value = true
  try {
    const data = await saveParentStyle(childId.value, parentStyleUseDefault.value, parentStyleCustomRules.value)
    parentStyleUseDefault.value = data.use_default
    parentStyleCustomRules.value = data.custom_rules || ''
    parentStyleDefaultRules.value = data.default_rules || parentStyleDefaultRules.value
    window.alert('家长设定已保存。')
  } catch (err) {
    const msg = err instanceof Error ? err.message : '保存家长设定失败。'
    window.alert(msg)
  } finally {
    parentStyleSaving.value = false
  }
}

async function initializePageState() {
  activePage.value = resolvePageFromLocation()
  window.addEventListener('popstate', () => {
    activePage.value = resolvePageFromLocation()
  })
  await Promise.all([syncVoices(), loadTodayMessages(), loadMailbox(), loadReport(), loadParentStyle()])
  mailboxPollTimer = window.setInterval(() => {
    void loadMailbox()
  }, 1500)
  voicePollTimer = window.setInterval(() => {
    void syncVoicesSafely()
  }, 2000)
  reportPollTimer = window.setInterval(() => {
    if (activePage.value === 'parent') void loadReport()
  }, 3000)
  await nextTick()
  scrollMessagesToBottom('auto')
  scrollMailboxToBottom('auto')
}

onMounted(() => {
  void initializePageState()
})

onUnmounted(() => {
  if (mailboxPollTimer) window.clearInterval(mailboxPollTimer)
  if (voicePollTimer) window.clearInterval(voicePollTimer)
  if (reportPollTimer) window.clearInterval(reportPollTimer)
})

watch(
  () => messages.value.length,
  async () => {
    await nextTick()
    scrollMessagesToBottom('smooth')
  }
)

watch(
  () => mailboxItems.value.length,
  async () => {
    await nextTick()
    scrollMailboxToBottom('smooth')
  }
)

function extractSeenObject(text: string): string {
  const cn = text.match(/(?:看见|看到|见到|遇到|发现)(?:了)?(.{1,12}?)(?:[，。！？?,]|$)/)
  if (cn?.[1]) return cn[1].replace(/^(一只|一条|一头|一个|一位|一群)/, '').trim()
  const en = text.match(/(?:i\s+saw|i\s+met|i\s+found)\s+([a-zA-Z\s]{1,20})(?:[\.,!?]|$)/i)
  if (en?.[1]) return en[1].replace(/^(a|an|the)\s+/i, '').trim()
  return ''
}

function buildFallbackTint(seedText: string): string {
  const seed = Math.abs([...seedText].reduce((n, c) => n + c.charCodeAt(0), 0)) % 360
  const c1 = `hsl(${seed}, 46%, 28%)`
  const c2 = `hsl(${(seed + 74) % 360}, 42%, 24%)`
  const c3 = `hsl(${(seed + 142) % 360}, 40%, 22%)`
  return `radial-gradient(circle at 18% 14%, ${c1} 0%, ${c2} 42%, ${c3} 100%)`
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
  const imageFile = selectedFile.value
  if (loading.value || (!text && !imageFile)) return

  if (imageFile) {
    messages.value.push({
      role: 'user',
      type: 'image',
      imageUrl: URL.createObjectURL(imageFile),
      text
    })
  } else {
    messages.value.push({ role: 'user', type: 'text', text })
  }
  input.value = ''
  selectedFile.value = null
  loading.value = true

  try {
    const data = imageFile
      ? await uploadImage(childId.value, text, imageFile, selectedVoiceId.value)
      : await sendChat({
          child_id: childId.value,
          message: text,
          enable_scene: true,
          enable_psych_analysis: true,
          voice_id: selectedVoiceId.value
        })
    const assistantAudioUrl = toAssetUrl(data.assistant_audio_url)
    messages.value.push({
      role: 'assistant',
      type: 'text',
      text: data.reply,
      audioUrl: assistantAudioUrl
    })
    playAudioUrl(assistantAudioUrl)
    if (data.scene_image_url && (!imageFile || extractSeenObject(text))) await applyScene(data.scene_image_url, text)
  } catch (err) {
    const msg = err instanceof Error ? err.message : '刚刚有点卡住了，我们再试一次。'
    messages.value.push({ role: 'assistant', type: 'text', text: msg })
  } finally {
    loading.value = false
  }
}

function onPickFile(e: Event) {
  const target = e.target as HTMLInputElement
  selectedFile.value = target.files?.[0] ?? null
}

function onPickVoiceFile(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0] ?? null
  if (!file) {
    voiceFile.value = null
    return
  }
  if (!file.name.toLowerCase().endsWith('.wav')) {
    window.alert('请选择 .wav 格式的音频文件。')
    target.value = ''
    return
  }
  voiceFile.value = file
}

function writeString(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) {
    view.setUint8(offset + i, value.charCodeAt(i))
  }
}

function audioBufferToWav(buffer: AudioBuffer): Blob {
  const channelCount = buffer.numberOfChannels
  const sampleRate = buffer.sampleRate
  const bytesPerSample = 2
  const frameCount = buffer.length
  const dataSize = frameCount * channelCount * bytesPerSample
  const arrayBuffer = new ArrayBuffer(44 + dataSize)
  const view = new DataView(arrayBuffer)
  let offset = 0

  writeString(view, offset, 'RIFF')
  offset += 4
  view.setUint32(offset, 36 + dataSize, true)
  offset += 4
  writeString(view, offset, 'WAVE')
  offset += 4
  writeString(view, offset, 'fmt ')
  offset += 4
  view.setUint32(offset, 16, true)
  offset += 4
  view.setUint16(offset, 1, true)
  offset += 2
  view.setUint16(offset, channelCount, true)
  offset += 2
  view.setUint32(offset, sampleRate, true)
  offset += 4
  view.setUint32(offset, sampleRate * channelCount * bytesPerSample, true)
  offset += 4
  view.setUint16(offset, channelCount * bytesPerSample, true)
  offset += 2
  view.setUint16(offset, 16, true)
  offset += 2
  writeString(view, offset, 'data')
  offset += 4
  view.setUint32(offset, dataSize, true)
  offset += 4

  const channels = Array.from({ length: channelCount }, (_, index) => buffer.getChannelData(index))
  for (let i = 0; i < frameCount; i += 1) {
    for (let channel = 0; channel < channelCount; channel += 1) {
      const sample = Math.max(-1, Math.min(1, channels[channel][i]))
      view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true)
      offset += 2
    }
  }

  return new Blob([view], { type: 'audio/wav' })
}

async function convertBlobToWavFile(blob: Blob, prefix = 'mic'): Promise<File> {
  const audioContext = new AudioContext()
  try {
    const audioData = await blob.arrayBuffer()
    const decoded = await audioContext.decodeAudioData(audioData)
    const wavBlob = audioBufferToWav(decoded)
    const stamp = new Date().toISOString().replace(/[-:.TZ]/g, '').slice(0, 14)
    return new File([wavBlob], `${prefix}-${stamp}.wav`, { type: 'audio/wav' })
  } finally {
    await audioContext.close()
  }
}

async function startVoiceRecording() {
  if (recording.value || loading.value) return
  if (!navigator.mediaDevices?.getUserMedia) {
    window.alert('当前浏览器不支持麦克风录音。')
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    recordingStream.value = stream
    recordedChunks.value = []
    const nextRecorder = new MediaRecorder(stream)
    recorder.value = nextRecorder

    nextRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) recordedChunks.value.push(event.data)
    }

    nextRecorder.onstop = async () => {
      recording.value = false
      recordingStream.value?.getTracks().forEach((track) => track.stop())
      recordingStream.value = null

      try {
        const sourceBlob = new Blob(recordedChunks.value, { type: nextRecorder.mimeType || 'audio/webm' })
        voiceFile.value = await convertBlobToWavFile(sourceBlob)
      } catch {
        window.alert('录音转换为 .wav 失败，请再录一次或选择本地 .wav 文件。')
      } finally {
        recordedChunks.value = []
      }
    }

    nextRecorder.start()
    recording.value = true
  } catch {
    window.alert('无法打开麦克风，请检查浏览器权限。')
  }
}

function stopVoiceRecording() {
  if (!recording.value) return
  recorder.value?.stop()
}

async function startMailboxRecording() {
  if (mailboxRecording.value || loading.value) return
  if (!navigator.mediaDevices?.getUserMedia) {
    window.alert('当前浏览器不支持麦克风录音。')
    return
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    mailboxStream.value = stream
    mailboxChunks.value = []
    const nextRecorder = new MediaRecorder(stream)
    mailboxRecorder.value = nextRecorder

    nextRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) mailboxChunks.value.push(event.data)
    }

    nextRecorder.onstop = async () => {
      mailboxRecording.value = false
      mailboxStream.value?.getTracks().forEach((track) => track.stop())
      mailboxStream.value = null

      try {
        const sourceBlob = new Blob(mailboxChunks.value, { type: nextRecorder.mimeType || 'audio/webm' })
        mailboxAudioFile.value = await convertBlobToWavFile(sourceBlob, 'mailbox')
      } catch {
        window.alert('留言录音转换为 .wav 失败，请再录一次。')
      } finally {
        mailboxChunks.value = []
      }
    }

    nextRecorder.start()
    mailboxRecording.value = true
  } catch {
    window.alert('无法打开麦克风，请检查浏览器权限。')
  }
}

function stopMailboxRecording() {
  if (!mailboxRecording.value) return
  mailboxRecorder.value?.stop()
}

async function sendMailbox() {
  const text = mailboxText.value.trim()
  if (loading.value || (!text && !mailboxAudioFile.value)) return

  loading.value = true
  try {
    const item = await sendMailboxItem(childId.value, mailboxSender.value, text, mailboxAudioFile.value)
    mailboxItems.value.push(item)
    mailboxText.value = ''
    mailboxAudioFile.value = null
  } catch (err) {
    const msg = err instanceof Error ? err.message : '发送留言失败。'
    window.alert(msg)
  } finally {
    loading.value = false
  }
}

async function clearMailboxForCurrentSide() {
  if (loading.value || confirmLoading.value) return
  confirmAction.value = 'clear-mailbox'
  confirmTitle.value = '确认清空留言'
  confirmMessage.value = '确定要清空留言吗？'
  confirmModalOpen.value = true
}

async function onEnrollVoice() {
  if (!voiceFile.value || loading.value) return
  loading.value = true
  try {
    const data = await enrollVoice(childId.value, voiceFile.value, voicePrefix.value)
    await syncVoices()
    window.alert(`人声注册完成：${data.voice_id}`)
  } catch (err) {
    const msg = err instanceof Error ? err.message : '人声注册失败，请确认样本可用并重试。'
    window.alert(msg)
  } finally {
    loading.value = false
    voiceFile.value = null
  }
}

async function onResetHistory() {
  if (loading.value || confirmLoading.value) return
  confirmAction.value = 'reset-history'
  confirmTitle.value = '确认清空历史记录'
  confirmMessage.value = '确定要清空历史记录吗？'
  confirmModalOpen.value = true
}

function closeConfirmModal(force = false) {
  if (confirmLoading.value && !force) return
  confirmModalOpen.value = false
  confirmAction.value = ''
  confirmTitle.value = ''
  confirmMessage.value = ''
}

async function executeConfirmedAction() {
  if (!confirmAction.value || confirmLoading.value) return

  confirmLoading.value = true
  loading.value = true
  try {
    if (confirmAction.value === 'clear-mailbox') {
      await clearMailbox(childId.value, mailboxSender.value)
      mailboxItems.value = []
    }

    if (confirmAction.value === 'reset-history') {
      await resetHistory()
      messages.value = [defaultMessage]
      report.value = null
      input.value = ''
      selectedFile.value = null
      sceneUrl.value = ''
    }

    closeConfirmModal(true)
  } catch (err) {
    const fallback = confirmAction.value === 'clear-mailbox' ? '清空留言失败。' : '清空历史记录失败。'
    const msg = err instanceof Error ? err.message : fallback
    window.alert(msg)
  } finally {
    loading.value = false
    confirmLoading.value = false
  }
}

async function openVoiceManager() {
  if (loading.value) return
  loading.value = true
  try {
    await syncVoices()
    voiceModalOpen.value = true
  } catch (err) {
    const msg = err instanceof Error ? err.message : '获取人声列表失败。'
    window.alert(msg)
  } finally {
    loading.value = false
  }
}

function closeVoiceManager() {
  if (deletingVoiceId.value) return
  voiceModalOpen.value = false
}

async function onDeleteVoice(voice: VoiceItem) {
  if (deletingVoiceId.value) return
  if (!window.confirm(`确认删除这条人声吗？\n${voice.voice_id}`)) return

  deletingVoiceId.value = voice.voice_id
  try {
    await deleteVoice(childId.value, voice.voice_id)
    registeredVoices.value = registeredVoices.value.filter((item) => item.voice_id !== voice.voice_id)
    if (selectedVoiceId.value === voice.voice_id) persistSelectedVoice('')
  } catch (err) {
    const msg = err instanceof Error ? err.message : '删除人声失败。'
    window.alert(msg)
  } finally {
    deletingVoiceId.value = ''
  }
}
</script>

<template>
  <div class="app" :style="sceneStyle">
    <main v-if="activePage === 'child'" class="page-grid child-page">
      <section class="conversation-panel glass">
        <div class="panel-heading">
          <div>
            <p class="eyebrow">陪伴对话</p>
            <h2>今天想聊什么都可以</h2>
          </div>
        </div>

        <div ref="messagesRef" class="messages">
          <article v-for="(m, idx) in messages" :key="idx" class="bubble" :class="m.role">
            <template v-if="m.type === 'image'">
              <img v-if="m.imageUrl" :src="m.imageUrl" alt="孩子上传的图片" class="bubble-image" />
              <p v-if="m.text" class="bubble-caption">{{ m.text }}</p>
            </template>
            <template v-else>
              <p>{{ m.text }}</p>
              <audio
                v-if="canShowAudio(m.audioUrl)"
                :src="m.audioUrl"
                controls
                preload="none"
                @error="markAudioUnavailable(m.audioUrl)"
              ></audio>
            </template>
          </article>
        </div>

        <div class="composer">
          <input v-model="input" placeholder="和爸爸妈妈说说今天发生了什么..." @keyup.enter="onSend" />
          <button @click="onSend" :disabled="loading || (!input.trim() && !selectedFile)">发送</button>
          <div class="chat-upload-row">
            <input type="file" accept="image/*" @change="onPickFile" />
            <button class="danger" @click="onResetHistory" :disabled="loading">清空历史记录</button>
            <p v-if="selectedFile" class="helper">已选择：{{ selectedFile.name }}</p>
          </div>
        </div>
      </section>

      <aside class="side-panel">
        <section class="voice-choice glass">
          <p class="eyebrow">声音选择</p>
          <h2>想听谁来回应？</h2>
          <select :value="selectedVoiceId" @change="onSelectVoice">
            <option value="">暂不使用人声</option>
            <option v-for="voice in registeredVoices" :key="voice.voice_id" :value="voice.voice_id">
              {{ voice.display_name }}
            </option>
          </select>
          <p class="helper">现在选择：{{ selectedVoiceName }}</p>
          <button class="secondary" @click="syncVoices" :disabled="loading">刷新声音</button>
        </section>

        <section class="mailbox-panel child-mailbox glass" :class="activePage">
          <p class="eyebrow">留言箱</p>
          <div ref="mailboxRef" class="mailbox-list">
            <article v-for="(item, idx) in mailboxItems" :key="`${item.timestamp}-${idx}`" class="mailbox-item" :class="item.sender">
              <p v-if="item.content">{{ item.content }}</p>
              <button
                v-if="item.message_type === 'audio' && item.audio_url"
                class="compact-audio"
                :aria-label="playingAudioKey === item.audio_url ? '停止语音' : '播放语音'"
                @click="playCompactAudio(item.audio_url)"
              >
                <span class="audio-icon" :class="{ playing: playingAudioKey === item.audio_url }"></span>
              </button>
            </article>
          </div>
          <input v-model="mailboxText" placeholder="写一条留言..." @keyup.enter="sendMailbox" />
          <div class="recorder-panel">
            <button class="secondary" @click="startMailboxRecording" :disabled="loading || mailboxRecording">语音留言</button>
            <button class="danger" @click="stopMailboxRecording" :disabled="!mailboxRecording">停止录音</button>
            <p v-if="mailboxRecording || mailboxAudioFile" class="helper">
              {{ mailboxRecording ? '正在录音...' : `已准备：${mailboxAudioFile?.name}` }}
            </p>
          </div>
          <div class="mailbox-actions">
            <button @click="sendMailbox" :disabled="loading || (!mailboxText.trim() && !mailboxAudioFile)">发送留言</button>
            <button class="danger" @click="clearMailboxForCurrentSide" :disabled="loading">清空留言</button>
          </div>
        </section>
      </aside>
    </main>

    <main v-else class="page-grid parent-page">
      <section class="parent-main-stack">
        <section class="report-panel glass">
          <div class="panel-heading">
            <div>
              <p class="eyebrow">心理日报</p>
              <h2>今天的情绪线索</h2>
            </div>
          </div>

          <div v-if="report" class="report">
            <div class="report-date">
              <span>{{ report.date }}</span>
              <strong>{{ report.total_messages }} 条对话</strong>
            </div>

            <div class="risk-grid">
              <article v-for="item in riskItems" :key="item.label" class="risk-tile">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </article>
            </div>

            <section class="suggestion-block">
              <p class="eyebrow">今晚可以这样回应</p>
              <p>{{ report.suggestion || '还没有形成建议，先刷新日报或让孩子多聊几句。' }}</p>
            </section>

            <ul class="highlight-list">
              <li v-for="(item, i) in report.highlights || []" :key="i">{{ item }}</li>
            </ul>
          </div>

          <div v-else class="empty-report">
            <p>这里会自动汇总孩子今天的对话、风险指标和陪伴建议。</p>
          </div>
        </section>

        <section class="voice-register glass">
          <p class="eyebrow">人声注册</p>

          <label>
            <span>声音名称</span>
            <input v-model="voicePrefix" placeholder="例如：妈妈、爸爸" />
          </label>

          <label>
            <span>音频样本</span>
            <input type="file" accept=".wav,audio/wav" @change="onPickVoiceFile" />
          </label>

          <div class="recorder-panel">
            <button class="secondary" @click="startVoiceRecording" :disabled="loading || recording">打开麦克风录音</button>
            <button class="danger" @click="stopVoiceRecording" :disabled="!recording">停止并转成 .wav</button>
            <p class="helper">
              {{ recording ? '正在录音...' : voiceFile ? `已准备：${voiceFile.name}` : '' }}
            </p>
          </div>

          <div class="voice-actions">
            <button @click="onEnrollVoice" :disabled="loading || !voiceFile">上传并注册</button>
            <button class="secondary" @click="openVoiceManager" :disabled="loading">管理人声</button>
          </div>
        </section>

        <section class="parent-style-panel glass">
          <p class="eyebrow">回复设定</p>
          <label class="style-choice">
            <input v-model="parentStyleUseDefault" type="checkbox" />
            <span>使用默认家长语气</span>
          </label>
          <textarea
            v-model="parentStyleCustomRules"
            :disabled="parentStyleUseDefault"
            placeholder="写下希望 AI 用什么语气、边界和回复方式。取消默认后生效。"
          ></textarea>
          <details class="default-style-preview">
            <summary>查看当前默认设定</summary>
            <p>{{ parentStyleDefaultRules }}</p>
          </details>
          <button @click="onSaveParentStyle" :disabled="parentStyleSaving">
            {{ parentStyleSaving ? '保存中...' : '保存设定' }}
          </button>
        </section>
      </section>

      <section class="mailbox-panel parent-mailbox glass" :class="activePage">
        <p class="eyebrow">留言箱</p>
        <div ref="mailboxRef" class="mailbox-list">
          <article v-for="(item, idx) in mailboxItems" :key="`${item.timestamp}-${idx}`" class="mailbox-item" :class="item.sender">
            <p v-if="item.content">{{ item.content }}</p>
            <button
              v-if="item.message_type === 'audio' && item.audio_url"
              class="compact-audio"
              :aria-label="playingAudioKey === item.audio_url ? '停止语音' : '播放语音'"
              @click="playCompactAudio(item.audio_url)"
            >
              <span class="audio-icon" :class="{ playing: playingAudioKey === item.audio_url }"></span>
            </button>
          </article>
        </div>
        <input v-model="mailboxText" placeholder="写一条留言..." @keyup.enter="sendMailbox" />
        <div class="recorder-panel">
          <button class="secondary" @click="startMailboxRecording" :disabled="loading || mailboxRecording">语音留言</button>
          <button class="danger" @click="stopMailboxRecording" :disabled="!mailboxRecording">停止录音</button>
          <p v-if="mailboxRecording || mailboxAudioFile" class="helper">
            {{ mailboxRecording ? '正在录音...' : `已准备：${mailboxAudioFile?.name}` }}
          </p>
        </div>
        <div class="mailbox-actions">
          <button @click="sendMailbox" :disabled="loading || (!mailboxText.trim() && !mailboxAudioFile)">发送留言</button>
          <button class="danger" @click="clearMailboxForCurrentSide" :disabled="loading">清空留言</button>
        </div>
      </section>
    </main>

    <div v-if="confirmModalOpen" class="confirm-modal-mask" @click.self="closeConfirmModal">
      <section class="confirm-modal glass" role="dialog" aria-modal="true" :aria-label="confirmTitle || '确认操作'">
        <header class="confirm-modal-header">
          <h3>{{ confirmTitle || '确认操作' }}</h3>
        </header>
        <p class="confirm-modal-text">{{ confirmMessage }}</p>
        <div class="confirm-modal-actions">
          <button class="secondary" @click="closeConfirmModal" :disabled="confirmLoading">取消</button>
          <button class="danger" @click="executeConfirmedAction" :disabled="confirmLoading">
            {{ confirmLoading ? '处理中...' : '确定' }}
          </button>
        </div>
      </section>
    </div>

    <div v-if="voiceModalOpen" class="voice-modal-mask" @click.self="closeVoiceManager">
      <section class="voice-modal glass" role="dialog" aria-modal="true" aria-label="已注册人声列表">
        <header class="voice-modal-header">
          <h3>已注册人声</h3>
          <button class="secondary" @click="closeVoiceManager" :disabled="!!deletingVoiceId">关闭</button>
        </header>

        <div v-if="registeredVoices.length === 0" class="voice-empty">当前没有可删除的人声。</div>

        <ul v-else class="voice-list">
          <li v-for="voice in registeredVoices" :key="voice.voice_id" class="voice-item">
            <div class="voice-meta">
              <p class="voice-id">{{ voice.display_name }}</p>
              <p class="voice-sub">ID：{{ voice.voice_id }}</p>
              <p class="voice-sub">前缀：{{ voice.prefix || '无' }} · 状态：{{ voice.status || '未知' }}</p>
              <p class="voice-sub">时间：{{ voice.timestamp || '-' }}</p>
            </div>
            <button
              class="danger"
              @click="onDeleteVoice(voice)"
              :disabled="deletingVoiceId === voice.voice_id"
            >
              {{ deletingVoiceId === voice.voice_id ? '删除中...' : '删除' }}
            </button>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
