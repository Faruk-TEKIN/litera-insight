import { ensureOk, getBackendBaseUrl } from './client';
import { getAuthHeaders } from '../lib/auth';

export interface TelegramStatus {
  configured: boolean;
  linked: boolean;
  telegram_username?: string | null;
  is_enabled: boolean;
  linked_at?: string | null;
  last_error?: string | null;
}

export interface TelegramLinkToken {
  bot_username: string;
  link_url: string;
  expires_at: string;
}

export async function fetchTelegramStatus(): Promise<TelegramStatus> {
  const response = await fetch(`${getBackendBaseUrl()}/telegram/status`, {
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function createTelegramLinkToken(): Promise<TelegramLinkToken> {
  const response = await fetch(`${getBackendBaseUrl()}/telegram/link-token`, {
    method: 'POST',
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
  return response.json();
}

export async function unlinkTelegram(): Promise<void> {
  const response = await fetch(`${getBackendBaseUrl()}/telegram/link`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  await ensureOk(response);
}
