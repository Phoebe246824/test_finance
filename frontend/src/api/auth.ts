import { http } from './http'

export interface AuthUser {
  username: string
  role: string
}

export async function loginWithToken(token: string): Promise<AuthUser & { access_token: string }> {
  const { data } = await http.post('/api/auth/login', { token })
  return data
}

export async function getMe(): Promise<AuthUser> {
  const { data } = await http.get('/api/auth/me')
  return data
}
