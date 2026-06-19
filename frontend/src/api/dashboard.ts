import { http } from './http'

export async function getDashboardOverview() {
  const { data } = await http.get('/api/dashboard/overview')
  return data
}
