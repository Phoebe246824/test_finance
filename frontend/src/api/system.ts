import { http } from './http'

export async function getHealth() {
  const { data } = await http.get('/api/system/health')
  return data
}

export async function getHardware() {
  const { data } = await http.get('/api/system/hardware')
  return data
}

export async function getRuntime() {
  const { data } = await http.get('/api/system/runtime')
  return data
}
