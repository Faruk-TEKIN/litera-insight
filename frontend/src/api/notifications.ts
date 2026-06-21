import { ensureOk, getBackendBaseUrl } from './client';
import { getAuthHeaders } from '../lib/auth';

export interface NotificationItem {
  id: number;
  type: string;
  title: string;
  body: string;
  payload: Record<string, unknown>;
  related_snapshot_key?: string | null;
  read_at?: string | null;
  created_at?: string | null;
}

export interface NotificationsResponse {
  items: NotificationItem[];
  unread_count: number;
}

export async function fetchNotifications(limit = 20): Promise<NotificationsResponse> {
  const response = await fetch(`${getBackendBaseUrl()}/notifications?limit=${limit}`, {
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function markNotificationRead(notificationId: number): Promise<NotificationItem> {
  const response = await fetch(`${getBackendBaseUrl()}/notifications/${notificationId}/read`, {
    method: 'PATCH',
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function markAllNotificationsRead(): Promise<{ updated: number; unread_count: number }> {
  const response = await fetch(`${getBackendBaseUrl()}/notifications/read-all`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
  return response.json();
}
