<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'

const props = defineProps({
  api: { type: String, required: true },
  token: { type: String, required: true },
  user: { type: Object, required: true },
})
const emit = defineEmits(['unauthorized'])

const models = ref([])
const sessions = ref([])
const currentSession = ref(null)
const messages = ref([])
const attachments = ref([])
const selectedModelId = ref('')
const prompt = ref('')
const busy = ref(false)
const uploadBusy = ref(false)
const error = ref('')
const showLinkInput = ref(false)
const linkUrl = ref('')
const linkBusy = ref(false)
const caseViewer = ref(null)
const showModelDialog = ref(false)
const modelSaving = ref(false)
const editingId = ref(null)
const connectionMessage = ref('')
const messageList = ref(null)
const modelForm = ref({
  name: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1',
  model_name: '', api_key: '', api_style: 'responses',
})

const currentModelId = computed({
  get: () => currentSession.value?.model_config_id || selectedModelId.value,
  set: async (value) => {
    selectedModelId.value = Number(value)
    if (!currentSession.value) return
    try {
      await request(`/api/ai/sessions/${currentSession.value.id}`, {
        method: 'PATCH', body: JSON.stringify({ model_config_id: Number(value) }),
      })
      currentSession.value.model_config_id = Number(value)
    } catch (requestError) {
      error.value = requestError.message
    }
  },
})

async function request(path, options = {}) {
  const response = await fetch(`${props.api}${path}`, {
    headers: { Authorization: `Bearer ${props.token}`, ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }), ...options.headers },
    ...options,
  })
  if (response.status === 401) emit('unauthorized')
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try { detail = (await response.json()).detail || detail } catch {}
    throw new Error(detail)
  }
  if (response.status === 204) return null
  return response.json()
}

async function loadInitial() {
  try {
    [models.value, sessions.value] = await Promise.all([
      request('/api/ai/models'), request('/api/ai/sessions'),
    ])
    if (models.value[0]) selectedModelId.value = models.value[0].id
    if (sessions.value[0]) await selectSession(sessions.value[0])
  } catch (requestError) {
    error.value = requestError.message
  }
}

async function refreshSessions() {
  sessions.value = await request('/api/ai/sessions')
}

async function createSession() {
  if (!models.value.length) {
    if (props.user.role === 'admin') showModelDialog.value = true
    error.value = props.user.role === 'admin' ? '请先添加一个大模型配置' : '暂无可用模型，请联系管理员配置'
    return
  }
  error.value = ''
  const session = await request('/api/ai/sessions', {
    method: 'POST',
    body: JSON.stringify({ title: '新会话', model_config_id: Number(selectedModelId.value || models.value[0].id) }),
  })
  sessions.value.unshift(session)
  await selectSession(session)
}

async function selectSession(session) {
  currentSession.value = session
  selectedModelId.value = session.model_config_id || selectedModelId.value
  error.value = ''
  const data = await request(`/api/ai/sessions/${session.id}/messages`)
  messages.value = data.messages
  attachments.value = data.attachments
  await scrollToBottom()
}

async function uploadFiles(event) {
  const files = [...(event.target.files || [])]
  event.target.value = ''
  if (!files.length || !currentSession.value) return
  uploadBusy.value = true
  error.value = ''
  try {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    const uploaded = await request(`/api/ai/sessions/${currentSession.value.id}/attachments`, {
      method: 'POST', body: form,
    })
    attachments.value.push(...uploaded)
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    uploadBusy.value = false
  }
}

async function addLink() {
  const url = linkUrl.value.trim()
  if (!url || linkBusy.value || !currentSession.value) return
  linkBusy.value = true
  error.value = ''
  try {
    const attachment = await request(`/api/ai/sessions/${currentSession.value.id}/links`, {
      method: 'POST', body: JSON.stringify({ url }),
    })
    attachments.value.push(attachment)
    linkUrl.value = ''
    showLinkInput.value = false
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    linkBusy.value = false
  }
}

async function sendMessage() {
  const content = prompt.value.trim()
  if (!content || busy.value) return
  if (!currentSession.value) await createSession()
  if (!currentSession.value) return
  busy.value = true
  error.value = ''
  prompt.value = ''
  messages.value.push({ id: `temp-${Date.now()}`, role: 'user', content })
  await scrollToBottom()
  try {
    const message = await request(`/api/ai/sessions/${currentSession.value.id}/chat`, {
      method: 'POST', body: JSON.stringify({ content }),
    })
    messages.value.push(message)
    await refreshSessions()
    const refreshed = sessions.value.find((item) => item.id === currentSession.value.id)
    if (refreshed) currentSession.value = refreshed
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    busy.value = false
    await scrollToBottom()
  }
}

function handlePromptKeydown(event) {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault()
    sendMessage()
  }
}

function displayContent(message) {
  if (!message.structured) return message.content
  return message.content.replace(/```json[\s\S]*?```/i, '').trim() || '测试用例已生成。'
}

function formatSize(bytes) {
  return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)}KB` : `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

async function exportCases(format, messageId = null) {
  if (!currentSession.value) return
  error.value = ''
  try {
    const suffix = messageId ? `&message_id=${messageId}` : ''
    const response = await fetch(`${props.api}/api/ai/sessions/${currentSession.value.id}/export?format=${format}${suffix}`, { headers: { Authorization: `Bearer ${props.token}` } })
    if (!response.ok) {
      const data = await response.json()
      throw new Error(data.detail || '导出失败')
    }
    const blob = await response.blob()
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `test-cases-${currentSession.value.id}.${format}`
    link.click()
    URL.revokeObjectURL(url)
  } catch (requestError) { error.value = requestError.message }
}

function applyProviderPreset() {
  if (modelForm.value.provider === 'openai') {
    modelForm.value.base_url = 'https://api.openai.com/v1'
    modelForm.value.api_style = 'responses'
  } else {
    modelForm.value.base_url = ''
    modelForm.value.api_style = 'chat_completions'
  }
}

function resetModelForm() {
  editingId.value = null
  modelForm.value = { name: 'OpenAI', provider: 'openai', base_url: 'https://api.openai.com/v1', model_name: '', api_key: '', api_style: 'responses' }
}

function startEdit(model) {
  editingId.value = model.id
  modelForm.value = {
    name: model.name, provider: model.provider || 'openai_compatible',
    base_url: model.base_url || '', model_name: model.model_name || '',
    api_key: '', api_style: model.api_style || 'chat_completions',
  }
  connectionMessage.value = ''
  showModelDialog.value = true
}

async function saveModel() {
  modelSaving.value = true
  error.value = ''
  try {
    if (editingId.value) {
      const payload = { ...modelForm.value }
      if (!payload.api_key) delete payload.api_key
      const updated = await request(`/api/ai/models/${editingId.value}`, {
        method: 'PATCH', body: JSON.stringify(payload),
      })
      const index = models.value.findIndex((item) => item.id === editingId.value)
      if (index >= 0) models.value.splice(index, 1, updated)
      await refreshSessions()
      const refreshed = sessions.value.find((item) => item.id === currentSession.value?.id)
      if (refreshed) currentSession.value = refreshed
      showModelDialog.value = false
      resetModelForm()
    } else {
      const model = await request('/api/ai/models', { method: 'POST', body: JSON.stringify(modelForm.value) })
      models.value.unshift(model)
      selectedModelId.value = model.id
      showModelDialog.value = false
      resetModelForm()
    }
  } catch (requestError) {
    error.value = requestError.message
  } finally {
    modelSaving.value = false
  }
}

async function deleteModel(model) {
  if (!window.confirm(`删除模型配置「${model.name}」？正在使用它的会话需要重新选择模型。`)) return
  error.value = ''
  try {
    await request(`/api/ai/models/${model.id}`, { method: 'DELETE' })
    models.value = models.value.filter((item) => item.id !== model.id)
    if (editingId.value === model.id) { editingId.value = null; showModelDialog.value = false }
    await refreshSessions()
    const refreshed = sessions.value.find((item) => item.id === currentSession.value?.id)
    if (refreshed) currentSession.value = refreshed
  } catch (requestError) {
    error.value = requestError.message
  }
}

async function testModel(model) {
  connectionMessage.value = '正在测试连接…'
  try {
    const result = await request(`/api/ai/models/${model.id}/test`, { method: 'POST' })
    connectionMessage.value = `连接成功：${result.message}`
  } catch (requestError) {
    connectionMessage.value = requestError.message
  }
}

async function scrollToBottom() {
  await nextTick()
  if (messageList.value) messageList.value.scrollTop = messageList.value.scrollHeight
}

onMounted(loadInitial)
</script>

<template>
  <section class="agent-shell">
    <aside class="session-sidebar">
      <div class="session-heading"><div><p class="eyebrow">LANGGRAPH AGENT</p><h2>AI 测试设计</h2></div><button class="new-chat" title="新建会话" @click="createSession">＋</button></div>
      <button
        v-for="session in sessions" :key="session.id"
        class="session-item" :class="{ active: currentSession?.id === session.id }"
        @click="selectSession(session)"
      ><strong>{{ session.title }}</strong><small>{{ session.owner_username ? `${session.owner_username} · ` : '' }}{{ session.model_name || '未选择模型' }}</small></button>
      <div v-if="!sessions.length" class="session-empty">还没有会话<br>点击右上角 ＋ 开始</div>
    </aside>

    <section class="agent-main">
      <header class="agent-header">
        <div><h3>{{ currentSession?.title || '测试用例生成 Agent' }}</h3><p>ReAct · 会话记忆 · 附件理解</p></div>
        <div class="agent-actions">
          <select v-model="currentModelId" :disabled="!models.length"><option value="" disabled>选择模型</option><option v-for="model in models" :key="model.id" :value="model.id">{{ model.name }} / {{ model.model_name }}</option></select>
          <button v-if="user.role === 'admin'" class="secondary" @click="showModelDialog = true">模型配置</button>
          <button class="secondary" :disabled="!currentSession" @click="exportCases('xlsx')">导出 Excel</button>
          <button class="secondary" :disabled="!currentSession" @click="exportCases('xmind')">导出 XMind</button>
        </div>
      </header>

      <div ref="messageList" class="message-list">
        <div v-if="!currentSession" class="agent-welcome"><span>✦</span><h3>从需求到测试用例</h3><p>添加模型配置、创建会话，并上传 PRD、接口文档或已有用例。</p><button class="primary" @click="createSession">新建会话</button></div>
        <template v-else>
          <div v-if="!messages.length" class="agent-welcome compact"><span>✦</span><h3>描述你的测试任务</h3><p>例如：“根据附件生成登录、注册和找回密码的完整测试用例。”</p></div>
          <article v-for="message in messages" :key="message.id" class="chat-message" :class="message.role">
            <div class="avatar">{{ message.role === 'user' ? '你' : 'AI' }}</div>
            <div class="message-body"><p>{{ displayContent(message) }}</p>
              <div v-if="message.structured" class="case-result" title="点击查看全部用例" @click="caseViewer = message"><div class="case-summary"><strong>{{ message.structured.suite_name }}</strong><span>{{ message.structured.cases.length }} 条用例</span></div><p>{{ message.structured.summary }}</p><div class="case-preview"><span v-for="item in message.structured.cases.slice(0, 6)" :key="item.title"><b>{{ item.priority }}</b>{{ item.title }}</span></div><small class="case-open-hint">点击查看全部 {{ message.structured.cases.length }} 条用例并导出 →</small></div>
            </div>
          </article>
          <article v-if="busy" class="chat-message assistant"><div class="avatar">AI</div><div class="thinking"><i></i><i></i><i></i><span>Agent 正在分析需求并规划用例…</span></div></article>
        </template>
      </div>

      <footer class="agent-composer">
        <div v-if="attachments.length" class="attachment-list"><span v-for="file in attachments" :key="file.id">📎 {{ file.original_name }} <small>{{ formatSize(file.size) }}</small></span></div>
        <p v-if="error" class="agent-error">{{ error }}</p>
        <div v-if="showLinkInput" class="link-row">
          <input v-model="linkUrl" type="url" placeholder="粘贴需求文档链接（http/https），抓取后作为附件参与分析" :disabled="linkBusy" @keydown.enter.prevent="addLink">
          <button class="secondary" :disabled="linkBusy || !linkUrl.trim()" @click="addLink">{{ linkBusy ? '抓取中…' : '读取链接' }}</button>
        </div>
        <div class="composer-box">
          <label class="attach-button" :class="{ disabled: !currentSession || uploadBusy }"><input type="file" multiple accept=".txt,.md,.json,.yaml,.yml,.xml,.html,.log,.csv,.pdf,.docx,.xlsx" @change="uploadFiles">{{ uploadBusy ? '…' : '＋' }}</label>
          <button type="button" class="attach-button" :class="{ active: showLinkInput }" title="读取需求链接" @click="showLinkInput = !showLinkInput">🔗</button>
          <textarea v-model="prompt" :disabled="busy" rows="2" placeholder="输入测试需求，Shift + Enter 换行…" @keydown="handlePromptKeydown"></textarea>
          <button class="send-button" :disabled="busy || !prompt.trim()" @click="sendMessage">发送</button>
        </div>
        <small class="composer-hint">附件最大 10MB（PDF、Word、Excel、CSV、Markdown 等）· 🔗 支持抓取公网需求链接 · 对话中直接粘贴链接也可以</small>
      </footer>
    </section>
  </section>

  <div v-if="showModelDialog" class="modal-backdrop" @click.self="showModelDialog = false">
    <section class="model-modal">
      <div class="modal-title"><div><h3>大模型配置</h3><p>API Key 加密保存，不会返回到浏览器</p></div><button @click="showModelDialog = false">×</button></div>
      <div v-if="models.length" class="configured-models"><div v-for="model in models" :key="model.id"><span><strong>{{ model.name }}</strong><small>{{ model.model_name }} · {{ model.base_url }}</small></span><span class="model-row-actions"><button class="secondary" @click="testModel(model)">测试连接</button><button class="secondary" @click="startEdit(model)">编辑</button><button class="secondary danger" @click="deleteModel(model)">删除</button></span></div></div>
      <p v-if="connectionMessage" class="connection-message">{{ connectionMessage }}</p>
      <div class="divider"><span>{{ editingId ? '修改配置' : '添加配置' }}</span></div>
      <form class="model-form" @submit.prevent="saveModel">
        <div class="form-group"><label>服务类型</label><select v-model="modelForm.provider" @change="applyProviderPreset"><option value="openai">OpenAI / Codex</option><option value="step_dimension">跃迁维度（兼容接口）</option><option value="openai_compatible">其他 OpenAI-compatible</option></select></div>
        <div class="form-group"><label>配置名称</label><input v-model="modelForm.name" required placeholder="例如：Codex 生产模型"></div>
        <div class="form-group full"><label>Base URL</label><input v-model="modelForm.base_url" required placeholder="https://api.example.com/v1"></div>
        <div class="form-group"><label>模型 ID</label><input v-model="modelForm.model_name" required placeholder="填写账号实际可用的模型 ID"></div>
        <div class="form-group"><label>API 模式</label><select v-model="modelForm.api_style"><option value="responses">Responses API</option><option value="chat_completions">Chat Completions</option></select></div>
        <div class="form-group full"><label>API Key</label><input v-model="modelForm.api_key" :required="!editingId" type="password" autocomplete="new-password" :placeholder="editingId ? '留空则保持原有 Key 不变' : 'sk-...'"></div>
        <div class="full model-form-actions">
          <button v-if="editingId" type="button" class="secondary" @click="resetModelForm">取消修改</button>
          <button class="primary" :disabled="modelSaving">{{ modelSaving ? '保存中…' : (editingId ? '保存修改' : '保存模型配置') }}</button>
        </div>
      </form>
    </section>
  </div>

  <div v-if="caseViewer" class="modal-backdrop" @click.self="caseViewer = null">
    <section class="case-modal">
      <div class="modal-title">
        <div><h3>{{ caseViewer.structured.suite_name }}</h3><p>{{ caseViewer.structured.summary }}</p></div>
        <button @click="caseViewer = null">×</button>
      </div>
      <div class="case-toolbar">
        <span class="case-count">共 {{ caseViewer.structured.cases.length }} 条用例</span>
        <div class="case-toolbar-actions">
          <button class="secondary" @click="exportCases('xlsx', caseViewer.id)">导出 Excel</button>
          <button class="secondary" @click="exportCases('xmind', caseViewer.id)">导出 XMind</button>
        </div>
      </div>
      <div class="case-table-wrap">
        <table class="case-table">
          <thead><tr><th>优先级</th><th>模块</th><th>用例标题</th><th>测试编号</th><th>类型</th><th>前置条件</th><th>操作步骤</th><th>预期结果</th></tr></thead>
          <tbody>
            <tr v-for="(item, index) in caseViewer.structured.cases" :key="index">
              <td><span class="prio" :class="`p-${(item.priority || 'p3').toLowerCase()}`">{{ item.priority || '-' }}</span></td>
              <td>{{ item.module || '-' }}</td>
              <td class="case-title">{{ item.title }}</td>
              <td><span class="case-no">TC-{{ String(index + 1).padStart(3, '0') }}</span></td>
              <td>{{ item.type || '-' }}</td>
              <td>{{ item.preconditions || '-' }}</td>
              <td><ol v-if="item.steps && item.steps.length"><li v-for="(step, stepIndex) in item.steps" :key="stepIndex">{{ step }}</li></ol><span v-else>-</span></td>
              <td>{{ item.expected_result || '-' }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>
