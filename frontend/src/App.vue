<script setup>
import { onMounted, ref } from 'vue'
import Toolbox from './components/Toolbox.vue'
import AgentStudio from './components/AgentStudio.vue'
import LoginPage from './components/LoginPage.vue'
import AdminPanel from './components/AdminPanel.vue'

const currentPage = ref('dashboard')
const projects = ref([])
const cases = ref([])
const loading = ref(true)
const apiOnline = ref(false)
const api = import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? window.location.origin : `${window.location.protocol}//${window.location.hostname}:8000`)
const authToken = ref(sessionStorage.getItem('testpilot_token') || '')
const currentUser = ref(null)
const authLoading = ref(true)

async function apiRequest(path, options = {}) {
  const response = await fetch(`${api}${path}`, {
    ...options,
    headers: { Authorization: `Bearer ${authToken.value}`, 'Content-Type': 'application/json', ...options.headers },
  })
  if (response.status === 401) {
    logout()
    throw new Error('登录已失效')
  }
  return response
}

async function loadData() {
  loading.value = true
  try {
    const projectResponse = await apiRequest('/api/projects')
    if (!projectResponse.ok) throw new Error('API 请求失败')
    apiOnline.value = true
    projects.value = await projectResponse.json()
    if (projects.value[0]) {
      const caseResponse = await apiRequest(`/api/projects/${projects.value[0].id}/test-cases`)
      cases.value = await caseResponse.json()
    }
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

function authenticated(data) {
  authToken.value = data.access_token
  currentUser.value = data.user
  sessionStorage.setItem('testpilot_token', data.access_token)
  authLoading.value = false
  loadData()
}

function logout() {
  authToken.value = ''
  currentUser.value = null
  sessionStorage.removeItem('testpilot_token')
  currentPage.value = 'dashboard'
}

async function restoreSession() {
  if (!authToken.value) { authLoading.value = false; return }
  try {
    const response = await apiRequest('/api/auth/me')
    if (!response.ok) throw new Error('认证失败')
    currentUser.value = await response.json()
    await loadData()
  } catch { logout() } finally { authLoading.value = false }
}

onMounted(restoreSession)
</script>

<template>
  <div v-if="authLoading" class="app-loading">正在验证登录状态…</div>
  <LoginPage v-else-if="!currentUser" :api="api" @authenticated="authenticated" />
  <main v-else class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">QUALITY ENGINEERING</p>
        <h1>TestPilot</h1>
      </div>
      <nav class="main-nav">
        <button :class="{ active: currentPage === 'dashboard' }" @click="currentPage = 'dashboard'">工作台</button>
        <button :class="{ active: currentPage === 'agent' }" @click="currentPage = 'agent'">AI 测试 Agent</button>
        <button :class="{ active: currentPage === 'tools' }" @click="currentPage = 'tools'">B2C 工具箱</button>
        <button v-if="currentUser.role === 'admin'" :class="{ active: currentPage === 'admin' }" @click="currentPage = 'admin'">管理</button>
      </nav>
      <div class="account-menu"><span>{{ currentUser.display_name }}</span><button @click="logout">退出</button></div>
    </header>

    <template v-if="currentPage === 'dashboard'">
    <section class="hero">
      <div>
        <p class="eyebrow">测试平台 MVP</p>
        <h2>让每次发布，都有可追溯的质量证据。</h2>
        <p class="muted">统一管理接口用例、测试环境与执行结果，为 CI/CD 提供质量门禁。</p>
      </div>
      <div class="health" :class="{ offline: !apiOnline }"><span></span> {{ apiOnline ? 'API 服务正常' : 'API 暂未连接' }}</div>
    </section>

    <section class="stats">
      <article><span>项目</span><strong>{{ projects.length }}</strong></article>
      <article><span>测试用例</span><strong>{{ cases.length }}</strong></article>
      <article><span>最近通过率</span><strong>—</strong></article>
      <article><span>待处理失败</span><strong>—</strong></article>
    </section>

    <section class="panel">
      <div class="panel-heading"><h3>最近测试用例</h3><a href="#">查看全部</a></div>
      <div v-if="loading" class="empty">正在加载…</div>
      <div v-else-if="!cases.length" class="empty">暂无测试用例，先创建一个吧。</div>
      <div v-else class="case-list">
        <div v-for="item in cases" :key="item.id" class="case-row">
          <span class="method" :class="item.method.toLowerCase()">{{ item.method }}</span>
          <div><strong>{{ item.name }}</strong><small>{{ item.path }}</small></div>
          <span class="tag">{{ item.status }}</span>
        </div>
      </div>
    </section>
    </template>
    <AgentStudio v-else-if="currentPage === 'agent'" :api="api" :token="authToken" :user="currentUser" @unauthorized="logout" />
    <AdminPanel v-else-if="currentPage === 'admin' && currentUser.role === 'admin'" :api="api" :token="authToken" :current-user="currentUser" @unauthorized="logout" />
    <Toolbox v-else />
  </main>
</template>
