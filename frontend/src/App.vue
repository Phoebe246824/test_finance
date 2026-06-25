<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAppSettingsStore } from './stores/appSettings'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
const appSettings = useAppSettingsStore()
const router = useRouter()
const loginUsername = ref('admin')
const loginPassword = ref('admin')
const authError = ref('')
const loggingIn = ref(false)
const activeMenu = ref<'theme' | 'user' | ''>('')
const themeMode = ref<'light' | 'dark' | 'auto'>('light')

const navItems = [
  { to: '/dashboard', label: '首页总览', icon: 'home', arrow: false },
  { to: '/analysis', label: '风险分析', icon: 'chart', arrow: false },
  { to: '/events', label: '事件库', icon: 'doc', arrow: true },
  { to: '/blacklist', label: '黑名单管理', icon: 'user', arrow: true },
  { to: '/graph/person', label: '图谱查询', icon: 'graph', arrow: true },
  { to: '/system', label: '系统状态', icon: 'gear', arrow: true },
  { to: '/settings', label: '设置管理', icon: 'settings', arrow: true },
]

const showShell = computed(() => auth.isLoggedIn)

function toggleMenu(menu: 'theme' | 'user') {
  activeMenu.value = activeMenu.value === menu ? '' : menu
}

function setTheme(mode: 'light' | 'dark' | 'auto') {
  themeMode.value = mode
  activeMenu.value = ''
}

function logout() {
  activeMenu.value = ''
  auth.logout()
  router.push('/')
}

async function login() {
  if (!loginUsername.value.trim() || !loginPassword.value.trim()) return
  loggingIn.value = true
  authError.value = ''
  try {
    if (loginUsername.value.trim() !== 'admin' || loginPassword.value.trim() !== 'admin') {
      throw new Error('账号或密码错误')
    }
    await auth.login('sentinel-admin-token')
    await appSettings.load()
    await router.push('/dashboard')
  } catch (err: any) {
    authError.value = err?.response?.data?.detail || err?.message || '登录失败'
  } finally {
    loggingIn.value = false
  }
}

onMounted(() => {
  if (auth.isLoggedIn) appSettings.load().catch(() => undefined)
})
</script>

<template>
  <div v-if="showShell" class="app-shell">
    <aside class="sidebar">
      <div class="brand">
        <div class="brand-mark">
          <img src="/sentinel-edge-logo.svg" alt="Sentinel Edge logo" />
        </div>
        <div>
          <strong>{{ appSettings.appName }}</strong>
          <span>{{ appSettings.appDescription }}</span>
        </div>
      </div>
      <nav class="nav-list">
        <RouterLink v-for="item in navItems" :key="item.to" class="nav-link" :to="item.to">
          <span class="nav-icon">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path v-if="item.icon === 'home'" d="M3 11.5 12 4l9 7.5M5.5 10.5V20h13v-9.5M9 20v-6h6v6" />
              <path v-else-if="item.icon === 'chart'" d="M4 19h16M7 16V9m5 7V5m5 11v-4M5 7l4-3 4 4 5-5" />
              <path v-else-if="item.icon === 'doc'" d="M7 3h7l4 4v14H7zM14 3v5h5M9 12h6M9 16h6" />
              <path v-else-if="item.icon === 'user'" d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20c1.2-4 13.8-4 15 0M8 20h8" />
              <path v-else-if="item.icon === 'graph'" d="M6 18a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm12 0a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM12 8a3 3 0 1 0 0-6 3 3 0 0 0 0 6ZM8.5 13.5 11 8m2 0 2.5 5.5M9 15h6" />
              <path v-else-if="item.icon === 'gear'" d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm0-5v3m0 12v3M4.2 6.2l2.1 2.1m11.4 7.4 2.1 2.1M3 12h3m12 0h3M4.2 17.8l2.1-2.1m11.4-7.4 2.1-2.1" />
              <path v-else d="M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm8 4h2M2 12h2m13.7-5.7 1.4-1.4M4.9 19.1l1.4-1.4m0-11.4L4.9 4.9m14.2 14.2-1.4-1.4" />
            </svg>
          </span>
          <span>{{ item.label }}</span>
          <span v-if="item.arrow" class="nav-arrow">›</span>
        </RouterLink>
      </nav>
      <div class="sidebar-user">
        <span class="user-avatar">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM4.5 20c1.2-4 13.8-4 15 0" /></svg>
        </span>
        <div>
          <span>当前用户</span>
          <strong>{{ auth.isLoggedIn ? auth.username : '未登录' }}</strong>
        </div>
        <button v-if="auth.isLoggedIn" class="logout-link" @click="auth.logout">退出</button>
      </div>
    </aside>
    <div class="content-shell">
      <header class="app-topbar">
        <div></div>
        <div class="topbar-actions">
          <button class="topbar-icon has-badge" title="通知">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 7h18s-3 0-3-7M10 20h4" /></svg>
            <span class="topbar-badge">1</span>
          </button>
          <div class="topbar-menu-wrap">
            <button class="topbar-icon" title="显示模式" @click="toggleMenu('theme')">
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H4zM8 20h8M12 16v4" /></svg>
            </button>
            <div v-if="activeMenu === 'theme'" class="theme-popover">
              <button :class="{ active: themeMode === 'light' }" @click="setTheme('light')">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v2m0 12v2M4 12h2m12 0h2m-3.7-6.3-1.4 1.4M7.1 16.9l-1.4 1.4m0-12.6 1.4 1.4m7.8 7.8 1.4 1.4M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z" /></svg>
                <span><strong>浅色模式</strong><em>始终使用浅色主题</em></span>
              </button>
              <button :class="{ active: themeMode === 'dark' }" @click="setTheme('dark')">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 15.5A7.5 7.5 0 0 1 8.5 4 8.2 8.2 0 1 0 20 15.5Z" /></svg>
                <span><strong>深色模式</strong><em>始终使用深色主题</em></span>
              </button>
              <button :class="{ active: themeMode === 'auto' }" @click="setTheme('auto')">
                <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h16v11H4zM8 20h8M12 16v4" /></svg>
                <span><strong>自动模式</strong><em>跟随系统主题设置</em></span>
              </button>
              <p>当前跟随系统：{{ themeMode === 'dark' ? '深色' : '浅色' }}</p>
            </div>
          </div>
          <button class="topbar-icon" title="语言">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 8h9M9 4v4m1 0c-.8 4-2.7 7-5 9m4-6c1 1.6 2.3 3 4 4m3-2 3 7m-5 0 3-7 3 7m-5.2-2h4.4" /></svg>
          </button>
          <div class="topbar-menu-wrap">
            <button class="topbar-user" @click="toggleMenu('user')">
              <span>{{ auth.username.slice(0, 1).toUpperCase() || 'A' }}</span>
              <strong>{{ auth.username || 'admin' }}</strong>
              <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
            </button>
            <div v-if="activeMenu === 'user'" class="user-popover">
              <strong>{{ auth.username || 'admin' }}</strong>
              <span>{{ auth.role || 'admin' }}</span>
              <button @click="logout">退出登录</button>
            </div>
          </div>
        </div>
      </header>
      <main class="main">
        <RouterView />
      </main>
    </div>
  </div>

  <div v-else class="login-page">
    <div class="login-hero">
      <div class="login-mark">
        <img src="/sentinel-edge-logo.svg" alt="Sentinel Edge logo" />
      </div>
      <h1>{{ appSettings.appName }}</h1>
      <p>{{ appSettings.appDescription }}</p>
      <span>AI 驱动 · 端侧部署 · 智能风控</span>
    </div>
    <div class="login-panel">
      <h2>用户登录</h2>
      <p class="muted small">请输入您的账号和密码</p>
      <label class="login-input-shell">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20c1-4 13-4 14 0" /></svg>
        <input v-model="loginUsername" class="login-input" placeholder="admin" @keyup.enter="login" />
      </label>
      <label class="login-input-shell">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 10V8a5 5 0 0 1 10 0v2M6 10h12v10H6z" /></svg>
        <input v-model="loginPassword" class="login-input" type="password" placeholder="admin" @keyup.enter="login" />
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Zm10 3a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" /></svg>
      </label>
      <label class="login-remember">
        <input type="checkbox" checked />
        <span>记住我</span>
        <a href="#">忘记密码?</a>
      </label>
      <button class="login-button" :disabled="loggingIn" @click="login">
        {{ loggingIn ? '登录中' : '登录' }}
      </button>
      <p v-if="authError" class="sidebar-error">{{ authError }}</p>
      <p class="login-admin-tip">还没有账号？联系系统管理员</p>
    </div>
    <p class="login-footer">© 2026 {{ appSettings.appName }}<br />保留所有权利</p>
  </div>
</template>
