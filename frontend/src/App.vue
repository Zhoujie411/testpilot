<script setup>
import { onMounted, ref } from 'vue'
import Toolbox from './components/Toolbox.vue'

const currentPage = ref('dashboard')
const projects = ref([])
const cases = ref([])
const loading = ref(true)
const apiOnline = ref(false)
const api = import.meta.env.VITE_API_BASE_URL || `${window.location.protocol}//${window.location.hostname}:8000`

async function loadData() {
  loading.value = true
  try {
    const projectResponse = await fetch(`${api}/api/projects`)
    if (!projectResponse.ok) throw new Error('API 请求失败')
    apiOnline.value = true
    projects.value = await projectResponse.json()
    if (projects.value[0]) {
      const caseResponse = await fetch(`${api}/api/projects/${projects.value[0].id}/test-cases`)
      cases.value = await caseResponse.json()
    }
  } catch {
    apiOnline.value = false
  } finally {
    loading.value = false
  }
}

onMounted(loadData)
</script>

<template>
  <main class="shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">QUALITY ENGINEERING</p>
        <h1>TestPilot</h1>
      </div>
      <nav class="main-nav">
        <button :class="{ active: currentPage === 'dashboard' }" @click="currentPage = 'dashboard'">工作台</button>
        <button :class="{ active: currentPage === 'tools' }" @click="currentPage = 'tools'">B2C 工具箱</button>
      </nav>
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
    <Toolbox v-else />
  </main>
</template>
