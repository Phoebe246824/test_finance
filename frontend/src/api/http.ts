import axios from 'axios'

export const http = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000',
  timeout: 300000,
})

http.interceptors.request.use((config) => {
  const saved = localStorage.getItem('sentinel:auth')
  const token = saved ? JSON.parse(saved).token : ''
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})
