import { http } from './http'

export type NotificationChannel = {
  readonly name: string
  readonly enabled: boolean
  readonly target: string
}

export type NotificationChannelListResponse = {
  readonly channels: readonly NotificationChannel[]
  readonly total: number
}

export async function listNotificationChannels(): Promise<NotificationChannelListResponse> {
  const { data } = await http.get('/api/notifications')
  return data as NotificationChannelListResponse
}

export async function updateNotificationChannel(
  channelName: string,
  payload: { enabled: boolean; target: string },
): Promise<{ channel: NotificationChannel }> {
  const { data } = await http.put(
    `/api/notifications/${encodeURIComponent(channelName)}`,
    payload,
  )
  return data as { channel: NotificationChannel }
}

export async function testNotificationChannel(
  channelName: string,
): Promise<{ success: boolean; message: string; channel: string }> {
  const { data } = await http.post(
    `/api/notifications/${encodeURIComponent(channelName)}/test`,
  )
  return data as { success: boolean; message: string; channel: string }
}
