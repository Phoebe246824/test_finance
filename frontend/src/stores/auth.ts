import { defineStore } from 'pinia'
import { getMe, loginWithToken } from '../api/auth'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: '',
    username: '',
    role: '',
  }),
  getters: {
    isLoggedIn: (state) => Boolean(state.token),
    isAdmin: (state) => state.role === 'admin',
  },
  actions: {
    async login(token: string) {
      const user = await loginWithToken(token)
      this.token = user.access_token
      this.username = user.username
      this.role = user.role
    },
    async refresh() {
      if (!this.token) return
      const user = await getMe()
      this.username = user.username
      this.role = user.role
    },
    logout() {
      this.token = ''
      this.username = ''
      this.role = ''
    },
  },
})
