<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'

const activeTool = ref('timestamp')
const timestampInput = ref(String(Date.now()))
const dateInput = ref(toDateTimeLocal(new Date()))
const timestampError = ref('')

const compressFile = ref(null)
const compressTarget = ref(500)
const compressBusy = ref(false)
const compressMessage = ref('')
const compressResult = ref(null)

const cropFile = ref(null)
const cropWidth = ref(750)
const cropHeight = ref(750)
const cropBusy = ref(false)
const cropMessage = ref('')
const cropResult = ref(null)

const tools = [
  { id: 'timestamp', icon: '⌚', name: '时间戳转换', desc: '秒、毫秒与日期时间互转' },
  { id: 'compress', icon: '◫', name: '图片压缩', desc: '压缩至指定文件大小以内' },
  { id: 'crop', icon: '⌗', name: '图片裁切', desc: '居中裁切为指定像素尺寸' },
]

const parsedDate = computed(() => {
  timestampError.value = ''
  const raw = timestampInput.value.trim()
  if (!raw) return null
  let value
  if (/^\d{10}$/.test(raw)) value = Number(raw) * 1000
  else if (/^\d{13}$/.test(raw)) value = Number(raw)
  else {
    timestampError.value = '请输入 10 位秒级或 13 位毫秒级时间戳'
    return null
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    timestampError.value = '时间戳无效'
    return null
  }
  return date
})

const timestampDetails = computed(() => {
  if (!parsedDate.value) return null
  const date = parsedDate.value
  return {
    seconds: Math.floor(date.getTime() / 1000),
    milliseconds: date.getTime(),
    local: formatLocal(date),
    utc: date.toISOString().replace('T', ' ').replace('.000Z', ' UTC'),
  }
})

function toDateTimeLocal(date) {
  const offset = date.getTimezoneOffset() * 60_000
  return new Date(date.getTime() - offset).toISOString().slice(0, 19)
}

function formatLocal(date) {
  return new Intl.DateTimeFormat('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false,
  }).format(date).replaceAll('/', '-')
}

function useCurrentTime() {
  const now = new Date()
  timestampInput.value = String(now.getTime())
  dateInput.value = toDateTimeLocal(now)
}

function dateToTimestamp() {
  const date = new Date(dateInput.value)
  if (Number.isNaN(date.getTime())) {
    timestampError.value = '请选择有效的日期时间'
    return
  }
  timestampInput.value = String(date.getTime())
}

async function copyText(value) {
  const text = String(value)
  if (navigator.clipboard?.writeText && window.isSecureContext) {
    await navigator.clipboard.writeText(text)
    return
  }
  const input = document.createElement('textarea')
  input.value = text
  input.style.position = 'fixed'
  input.style.opacity = '0'
  document.body.appendChild(input)
  input.select()
  document.execCommand('copy')
  input.remove()
}

function selectCompressFile(event) {
  compressFile.value = event.target.files?.[0] || null
  clearResult(compressResult)
  compressMessage.value = ''
}

function selectCropFile(event) {
  cropFile.value = event.target.files?.[0] || null
  clearResult(cropResult)
  cropMessage.value = ''
}

function clearResult(resultRef) {
  if (resultRef.value?.url) URL.revokeObjectURL(resultRef.value.url)
  resultRef.value = null
}

function loadImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file)
    const image = new Image()
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('无法读取这张图片'))
    }
    image.src = url
  })
}

function canvasToBlob(canvas, type, quality) {
  return new Promise((resolve) => canvas.toBlob(resolve, type, quality))
}

async function compressImage() {
  if (!compressFile.value) {
    compressMessage.value = '请先选择一张图片'
    return
  }
  const targetBytes = Number(compressTarget.value) * 1024
  if (!targetBytes || targetBytes < 10 * 1024) {
    compressMessage.value = '目标大小不能低于 10KB'
    return
  }

  compressBusy.value = true
  compressMessage.value = ''
  clearResult(compressResult)
  try {
    const image = await loadImage(compressFile.value)
    const canvas = document.createElement('canvas')
    const context = canvas.getContext('2d')
    let scale = 1
    let best = null

    for (let resizeAttempt = 0; resizeAttempt < 8; resizeAttempt += 1) {
      canvas.width = Math.max(1, Math.round(image.naturalWidth * scale))
      canvas.height = Math.max(1, Math.round(image.naturalHeight * scale))
      context.fillStyle = '#ffffff'
      context.fillRect(0, 0, canvas.width, canvas.height)
      context.drawImage(image, 0, 0, canvas.width, canvas.height)

      let low = 0.05
      let high = 0.95
      let fitting = null
      for (let i = 0; i < 9; i += 1) {
        const quality = (low + high) / 2
        const blob = await canvasToBlob(canvas, 'image/jpeg', quality)
        if (blob.size <= targetBytes) {
          fitting = blob
          low = quality
        } else {
          high = quality
        }
      }
      if (fitting) {
        best = fitting
        break
      }

      const smallest = await canvasToBlob(canvas, 'image/jpeg', 0.05)
      const ratio = Math.sqrt(targetBytes / smallest.size) * 0.9
      scale *= Math.min(0.85, ratio)
    }

    if (!best) throw new Error('无法压缩到目标大小，请提高目标 KB 数')
    compressResult.value = {
      blob: best,
      url: URL.createObjectURL(best),
      name: `${fileBaseName(compressFile.value.name)}-compressed.jpg`,
      size: best.size,
      width: canvas.width,
      height: canvas.height,
    }
    compressMessage.value = '压缩完成'
  } catch (error) {
    compressMessage.value = error.message
  } finally {
    compressBusy.value = false
  }
}

async function cropImage() {
  if (!cropFile.value) {
    cropMessage.value = '请先选择一张图片'
    return
  }
  const width = Math.round(Number(cropWidth.value))
  const height = Math.round(Number(cropHeight.value))
  if (width < 1 || height < 1 || width > 8000 || height > 8000) {
    cropMessage.value = '宽高需在 1～8000 像素之间'
    return
  }

  cropBusy.value = true
  cropMessage.value = ''
  clearResult(cropResult)
  try {
    const image = await loadImage(cropFile.value)
    const canvas = document.createElement('canvas')
    canvas.width = width
    canvas.height = height
    const context = canvas.getContext('2d')
    const sourceRatio = image.naturalWidth / image.naturalHeight
    const targetRatio = width / height
    let sx = 0
    let sy = 0
    let sw = image.naturalWidth
    let sh = image.naturalHeight
    if (sourceRatio > targetRatio) {
      sw = image.naturalHeight * targetRatio
      sx = (image.naturalWidth - sw) / 2
    } else {
      sh = image.naturalWidth / targetRatio
      sy = (image.naturalHeight - sh) / 2
    }
    context.drawImage(image, sx, sy, sw, sh, 0, 0, width, height)
    const blob = await canvasToBlob(canvas, 'image/jpeg', 0.92)
    cropResult.value = {
      blob,
      url: URL.createObjectURL(blob),
      name: `${fileBaseName(cropFile.value.name)}-${width}x${height}.jpg`,
      size: blob.size,
      width,
      height,
    }
    cropMessage.value = '裁切完成'
  } catch (error) {
    cropMessage.value = error.message
  } finally {
    cropBusy.value = false
  }
}

function fileBaseName(name) {
  return name.replace(/\.[^.]+$/, '')
}

function formatBytes(bytes) {
  return bytes < 1024 * 1024
    ? `${(bytes / 1024).toFixed(1)} KB`
    : `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function downloadResult(result) {
  const link = document.createElement('a')
  link.href = result.url
  link.download = result.name
  link.click()
}

onBeforeUnmount(() => {
  clearResult(compressResult)
  clearResult(cropResult)
})
</script>

<template>
  <section class="tools-intro">
    <div>
      <p class="eyebrow">B2C TESTING TOOLBOX</p>
      <h2>测试小工具</h2>
      <p class="muted">常用数据与素材处理，全部在浏览器本地完成。</p>
    </div>
    <span class="privacy-badge">🔒 图片不会上传服务器</span>
  </section>

  <section class="tool-layout">
    <nav class="tool-nav" aria-label="工具列表">
      <button
        v-for="tool in tools"
        :key="tool.id"
        :class="{ active: activeTool === tool.id }"
        @click="activeTool = tool.id"
      >
        <span class="tool-icon">{{ tool.icon }}</span>
        <span><strong>{{ tool.name }}</strong><small>{{ tool.desc }}</small></span>
      </button>
    </nav>

    <div class="tool-workspace">
      <template v-if="activeTool === 'timestamp'">
        <div class="tool-title"><div><h3>时间戳转换</h3><p>支持 10 位秒级和 13 位毫秒级时间戳</p></div><button class="secondary" @click="useCurrentTime">使用当前时间</button></div>
        <div class="form-group">
          <label for="timestamp">时间戳</label>
          <input id="timestamp" v-model="timestampInput" inputmode="numeric" placeholder="例如：1730880000000">
          <p v-if="timestampError" class="form-error">{{ timestampError }}</p>
        </div>
        <div v-if="timestampDetails" class="result-grid">
          <div><span>本地时间</span><strong>{{ timestampDetails.local }}</strong><button @click="copyText(timestampDetails.local)">复制</button></div>
          <div><span>UTC 时间</span><strong>{{ timestampDetails.utc }}</strong><button @click="copyText(timestampDetails.utc)">复制</button></div>
          <div><span>秒级时间戳</span><strong>{{ timestampDetails.seconds }}</strong><button @click="copyText(timestampDetails.seconds)">复制</button></div>
          <div><span>毫秒级时间戳</span><strong>{{ timestampDetails.milliseconds }}</strong><button @click="copyText(timestampDetails.milliseconds)">复制</button></div>
        </div>
        <div class="divider"><span>日期转时间戳</span></div>
        <div class="inline-form"><div class="form-group"><label for="dateTime">本地日期时间</label><input id="dateTime" v-model="dateInput" type="datetime-local" step="1"></div><button class="primary" @click="dateToTimestamp">转换</button></div>
      </template>

      <template v-else-if="activeTool === 'compress'">
        <div class="tool-title"><div><h3>图片压缩</h3><p>输出为 JPG，自动调整画质和尺寸以满足目标大小</p></div></div>
        <label class="upload-zone">
          <input type="file" accept="image/*" @change="selectCompressFile">
          <span class="upload-icon">＋</span>
          <strong>{{ compressFile ? compressFile.name : '选择一张图片' }}</strong>
          <small>{{ compressFile ? `原文件 ${formatBytes(compressFile.size)}` : '支持 JPG、PNG、WebP 等常见格式' }}</small>
        </label>
        <div class="inline-form action-form"><div class="form-group"><label for="targetSize">目标大小（KB）</label><input id="targetSize" v-model.number="compressTarget" type="number" min="10" max="10240"></div><button class="primary" :disabled="compressBusy" @click="compressImage">{{ compressBusy ? '处理中…' : '开始压缩' }}</button></div>
        <p v-if="compressMessage" class="process-message">{{ compressMessage }}</p>
        <div v-if="compressResult" class="image-result">
          <img :src="compressResult.url" alt="压缩结果预览">
          <div><span>输出结果</span><strong>{{ formatBytes(compressResult.size) }}</strong><small>{{ compressResult.width }} × {{ compressResult.height }} px</small><button class="primary" @click="downloadResult(compressResult)">下载图片</button></div>
        </div>
      </template>

      <template v-else>
        <div class="tool-title"><div><h3>图片裁切</h3><p>按中心位置裁切，输出精确的像素尺寸</p></div></div>
        <label class="upload-zone">
          <input type="file" accept="image/*" @change="selectCropFile">
          <span class="upload-icon">＋</span>
          <strong>{{ cropFile ? cropFile.name : '选择一张图片' }}</strong>
          <small>{{ cropFile ? `原文件 ${formatBytes(cropFile.size)}` : '宽高比例不同时将自动居中裁切' }}</small>
        </label>
        <div class="dimension-form">
          <div class="form-group"><label for="cropWidth">宽度（px）</label><input id="cropWidth" v-model.number="cropWidth" type="number" min="1" max="8000"></div>
          <span>×</span>
          <div class="form-group"><label for="cropHeight">高度（px）</label><input id="cropHeight" v-model.number="cropHeight" type="number" min="1" max="8000"></div>
          <button class="primary" :disabled="cropBusy" @click="cropImage">{{ cropBusy ? '处理中…' : '开始裁切' }}</button>
        </div>
        <p v-if="cropMessage" class="process-message">{{ cropMessage }}</p>
        <div v-if="cropResult" class="image-result">
          <img :src="cropResult.url" alt="裁切结果预览">
          <div><span>输出结果</span><strong>{{ cropResult.width }} × {{ cropResult.height }} px</strong><small>{{ formatBytes(cropResult.size) }}</small><button class="primary" @click="downloadResult(cropResult)">下载图片</button></div>
        </div>
      </template>
    </div>
  </section>
</template>
