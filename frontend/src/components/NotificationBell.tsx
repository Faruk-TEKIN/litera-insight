import { useCallback, useEffect, useState } from 'react';
import { Bell, CheckCheck, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import {
  fetchNotifications,
  markAllNotificationsRead,
  markNotificationRead,
  type NotificationItem,
} from '../api/notifications';

interface NotificationBellProps {
  variant?: 'icon' | 'nav';
}

export function NotificationBell({ variant = 'icon' }: NotificationBellProps) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const loadNotifications = useCallback(async () => {
    setLoading(true);
    try {
      const data = await fetchNotifications(20);
      setItems(data.items);
      setUnreadCount(data.unread_count);
    } catch (error) {
      console.error('Unable to fetch notifications', error);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadNotifications();
    const listener = () => loadNotifications();
    window.addEventListener('notifications-updated', listener);
    const interval = window.setInterval(loadNotifications, 60000);
    return () => {
      window.removeEventListener('notifications-updated', listener);
      window.clearInterval(interval);
    };
  }, [loadNotifications]);

  const handleOpen = () => {
    setOpen((value) => !value);
    if (!open) {
      loadNotifications();
    }
  };

  const handleNotificationClick = async (item: NotificationItem) => {
    try {
      if (!item.read_at) {
        const updated = await markNotificationRead(item.id);
        setItems((prev) => prev.map((current) => current.id === item.id ? updated : current));
        setUnreadCount((count) => Math.max(count - 1, 0));
      }
    } catch (error) {
      console.error('Unable to mark notification as read', error);
    }

    const payload = item.payload || {};
    const selectionType = typeof payload.selection_type === 'string' ? payload.selection_type : null;
    const selectionId = typeof payload.selection_id === 'string' ? payload.selection_id : null;
    const weekStart = typeof payload.week_start === 'string' ? payload.week_start : null;
    const weekEnd = typeof payload.week_end === 'string' ? payload.week_end : null;
    const query = new URLSearchParams();
    if (selectionType) query.set('selection_type', selectionType);
    if (selectionId) query.set('selection_id', selectionId);
    if (weekStart) query.set('week_start', weekStart);
    if (weekEnd) query.set('week_end', weekEnd);
    const queryString = query.toString();
    setOpen(false);
    navigate(queryString ? `/bulletin?${queryString}` : '/bulletin');
  };

  const handleMarkAllRead = async () => {
    try {
      await markAllNotificationsRead();
      setItems((prev) => prev.map((item) => ({ ...item, read_at: item.read_at || new Date().toISOString() })));
      setUnreadCount(0);
    } catch (error) {
      console.error('Unable to mark notifications as read', error);
    }
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={handleOpen}
        className={
          variant === 'nav'
            ? 'relative flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] transition hover:bg-[var(--surface-elevated)] hover:text-[var(--text-primary)]'
            : 'relative inline-flex h-9 w-9 items-center justify-center rounded-lg border border-[var(--border)] text-[var(--text-secondary)] transition hover:bg-[var(--surface-high)] hover:text-[var(--text-primary)]'
        }
        aria-label="Notifications"
      >
        <Bell size={16} />
        {variant === 'nav' ? <span className="flex-1 text-left">Notifications</span> : null}
        {unreadCount > 0 ? (
          <span className={
            variant === 'nav'
              ? 'flex h-5 min-w-5 items-center justify-center rounded-full bg-rose-500 px-1.5 text-[10px] font-bold text-white'
              : 'absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white'
          }>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        ) : null}
      </button>

      {open ? (
        <div className={
          variant === 'nav'
            ? 'absolute left-0 top-12 z-50 w-[min(420px,calc(100vw-2rem))] overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)] shadow-xl md:left-0'
            : 'absolute bottom-11 left-0 z-50 w-80 overflow-hidden rounded-lg border border-[var(--border)] bg-[var(--surface)] shadow-xl md:bottom-auto md:left-auto md:right-0 md:top-11'
        }>
          <div className="flex items-center justify-between border-b border-[var(--border)] px-3 py-2">
            <div>
              <p className="text-sm font-semibold text-[var(--text-primary)]">Notifications</p>
              <p className="text-xs text-[var(--text-muted)]">{unreadCount} unread</p>
            </div>
            <button
              type="button"
              onClick={handleMarkAllRead}
              className="inline-flex h-8 items-center gap-1 rounded-md border border-[var(--border)] px-2 text-xs font-semibold text-[var(--text-secondary)] hover:bg-[var(--surface-elevated)]"
              title="Mark all read"
            >
              <CheckCheck size={13} />
              Read
            </button>
          </div>

          <div className="max-h-96 overflow-y-auto">
            {loading && !items.length ? (
              <div className="flex items-center justify-center py-8 text-[var(--text-muted)]">
                <Loader2 size={18} className="animate-spin" />
              </div>
            ) : items.length ? (
              items.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  onClick={() => handleNotificationClick(item)}
                  className={`block w-full border-b border-[var(--border-muted)] px-3 py-3 text-left transition hover:bg-[var(--surface-elevated)] ${
                    item.read_at ? '' : 'bg-emerald-500/5'
                  }`}
                >
                  <div className="flex items-start gap-2">
                    {!item.read_at ? <span className="mt-1.5 h-2 w-2 rounded-full bg-emerald-500" /> : <span className="mt-1.5 h-2 w-2" />}
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-[var(--text-primary)]">{item.title}</p>
                      <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{item.body}</p>
                      {item.created_at ? (
                        <p className="mt-1 text-[10px] uppercase tracking-[0.05em] text-[var(--text-muted)]">
                          {new Date(item.created_at).toLocaleString()}
                        </p>
                      ) : null}
                    </div>
                  </div>
                </button>
              ))
            ) : (
              <p className="px-3 py-8 text-center text-sm text-[var(--text-muted)]">No notifications yet.</p>
            )}
          </div>
        </div>
      ) : null}
    </div>
  );
}
