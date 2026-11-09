<script setup>
import { onMounted, ref } from 'vue'

const props = defineProps({ api: { type: String, required: true }, token: { type: String, required: true }, currentUser: { type: Object, required: true } })
const emit = defineEmits(['unauthorized'])
const users = ref([])
const error = ref('')
const busy = ref(false)
const form = ref({ username: '', display_name: '', password: '', role: 'user' })

async function request(path, options = {}) {
  const response = await fetch(`${props.api}${path}`, { ...options, headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${props.token}`, ...options.headers } })
  if (response.status === 401) emit('unauthorized')
  const data = await response.json()
  if (!response.ok) throw new Error(data.detail || '请求失败')
  return data
}
async function loadUsers() { try { users.value = await request('/api/admin/users') } catch (requestError) { error.value = requestError.message } }
async function createUser() {
  busy.value = true; error.value = ''
  try {
    const user = await request('/api/admin/users', { method: 'POST', body: JSON.stringify(form.value) })
    users.value.push(user)
    form.value = { username: '', display_name: '', password: '', role: 'user' }
  } catch (requestError) { error.value = requestError.message } finally { busy.value = false }
}
async function patchUser(user, changes) {
  error.value = ''
  try { Object.assign(user, await request(`/api/admin/users/${user.id}`, { method: 'PATCH', body: JSON.stringify(changes) })) }
  catch (requestError) { error.value = requestError.message }
}
async function resetPassword(user) {
  const password = window.prompt(`为 ${user.username} 设置新密码（至少 12 位）`)
  if (password) await patchUser(user, { password })
}
onMounted(loadUsers)
</script>

<template>
  <section class="admin-page">
    <div class="admin-intro"><div><p class="eyebrow">ADMINISTRATION</p><h2>用户与权限</h2><p class="muted">创建账号、分配管理员角色及停用访问权限。</p></div><span class="admin-badge">管理员模式</span></div>
    <div class="admin-grid">
      <section class="admin-card"><h3>创建用户</h3>
        <form class="admin-form" @submit.prevent="createUser">
          <div class="form-group"><label>用户名</label><input v-model="form.username" required minlength="3" pattern="[A-Za-z0-9_.-]+" placeholder="例如：tester01"></div>
          <div class="form-group"><label>显示名称</label><input v-model="form.display_name" required placeholder="例如：测试工程师"></div>
          <div class="form-group"><label>初始密码</label><input v-model="form.password" required minlength="12" type="password" autocomplete="new-password" placeholder="至少 12 位"></div>
          <div class="form-group"><label>角色</label><select v-model="form.role"><option value="user">普通用户</option><option value="admin">管理员</option></select></div>
          <p v-if="error" class="agent-error">{{ error }}</p><button class="primary" :disabled="busy">{{ busy ? '创建中…' : '创建账号' }}</button>
        </form>
      </section>
      <section class="admin-card user-table-card"><div class="admin-card-title"><h3>平台用户</h3><span>{{ users.length }} 个账号</span></div>
        <div class="user-table"><div v-for="user in users" :key="user.id" class="user-row">
          <span class="user-avatar">{{ user.display_name.slice(0, 1) }}</span><div class="user-info"><strong>{{ user.display_name }}</strong><small>@{{ user.username }} · {{ user.role === 'admin' ? '管理员' : '普通用户' }}</small></div>
          <span class="status-dot" :class="{ off: !user.is_active }">{{ user.is_active ? '正常' : '已停用' }}</span>
          <select :value="user.role" :disabled="user.id === currentUser.id" @change="patchUser(user, { role: $event.target.value })"><option value="user">普通用户</option><option value="admin">管理员</option></select>
          <button class="table-action" @click="resetPassword(user)">重置密码</button><button class="table-action" :disabled="user.id === currentUser.id" @click="patchUser(user, { is_active: !user.is_active })">{{ user.is_active ? '停用' : '启用' }}</button>
        </div></div>
      </section>
    </div>
  </section>
</template>
