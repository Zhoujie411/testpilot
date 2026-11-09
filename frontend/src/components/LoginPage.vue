<script setup>
import { ref } from 'vue'

const props = defineProps({ api: { type: String, required: true } })
const emit = defineEmits(['authenticated'])
const username = ref('')
const password = ref('')
const busy = ref(false)
const error = ref('')

async function login() {
  busy.value = true
  error.value = ''
  try {
    const response = await fetch(`${props.api}/api/auth/login`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: username.value.trim(), password: password.value }),
    })
    const data = await response.json()
    if (!response.ok) throw new Error(data.detail || '登录失败')
    emit('authenticated', data)
  } catch (requestError) { error.value = requestError.message } finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <section class="login-brand">
      <p class="eyebrow">QUALITY ENGINEERING PLATFORM</p><h1>TestPilot</h1>
      <h2>测试，不只是发现问题。</h2><p>统一管理自动化测试、B2C 工具与 AI 测试用例设计。</p>
      <div class="login-features"><span>✓ LangGraph Agent</span><span>✓ 会话记忆</span><span>✓ Excel / XMind</span></div>
    </section>
    <section class="login-card">
      <div><p class="eyebrow">SECURE ACCESS</p><h3>登录测试平台</h3><p>使用管理员分配的账号继续</p></div>
      <form @submit.prevent="login">
        <label>用户名<input v-model="username" required autocomplete="username" autofocus placeholder="请输入用户名"></label>
        <label>密码<input v-model="password" required type="password" autocomplete="current-password" placeholder="请输入密码"></label>
        <p v-if="error" class="login-error">{{ error }}</p>
        <button class="primary" :disabled="busy">{{ busy ? '正在验证…' : '安全登录' }}</button>
      </form>
      <small>登录状态仅保存在当前浏览器标签页</small>
    </section>
  </main>
</template>
