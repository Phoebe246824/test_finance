import { http } from './http'

export type ManagedUser = {
  readonly username: string
  readonly name: string
  readonly role: string
  readonly status: string
  readonly lastLogin: string
}

export type UserListResponse = {
  readonly users: readonly ManagedUser[]
  readonly total: number
}

export async function listUsers(): Promise<UserListResponse> {
  const { data } = await http.get('/api/users')
  return data as UserListResponse
}

export async function getUser(username: string): Promise<{ user: ManagedUser }> {
  const { data } = await http.get(`/api/users/${encodeURIComponent(username)}`)
  return data as { user: ManagedUser }
}

export async function createUser(payload: {
  username: string
  name: string
  role: string
  status?: string
  password?: string
}): Promise<{ user: ManagedUser }> {
  const { data } = await http.post('/api/users', payload)
  return data as { user: ManagedUser }
}

export async function updateUser(
  username: string,
  payload: { name: string; role: string },
): Promise<{ user: ManagedUser }> {
  const { data } = await http.put(`/api/users/${encodeURIComponent(username)}`, payload)
  return data as { user: ManagedUser }
}

export async function deleteUser(username: string): Promise<{ deleted: boolean; username: string }> {
  const { data } = await http.delete(`/api/users/${encodeURIComponent(username)}`)
  return data as { deleted: boolean; username: string }
}

export async function resetUserPassword(
  username: string,
  newPassword: string,
): Promise<{ user: ManagedUser }> {
  const { data } = await http.post(
    `/api/users/${encodeURIComponent(username)}/reset-password`,
    { new_password: newPassword },
  )
  return data as { user: ManagedUser }
}

export async function toggleUserStatus(username: string): Promise<{ user: ManagedUser }> {
  const { data } = await http.post(`/api/users/${encodeURIComponent(username)}/toggle-status`)
  return data as { user: ManagedUser }
}
