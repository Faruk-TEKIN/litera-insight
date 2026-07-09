# Optional Telegram PDF Notifications

Telegram delivery is an optional add-on. The core application runs without Telegram or ngrok. Enable it only if users want to receive Week's Best PDF bulletins on their phone.

## What This Feature Does

- Lets a signed-in user connect a Telegram chat from the Bulletin page.
- Sends an in-app notification whenever a validated Week's Best bulletin is generated.
- If Telegram is linked and configured, sends the generated PDF bulletin to the user's Telegram chat through the Celery worker.

## When Ngrok Is Required

Telegram webhooks must target a public HTTPS URL. Localhost is not reachable from Telegram.

- Local development: use ngrok through the Docker Compose `telegram` profile.
- Production or staging: use the real public HTTPS backend URL; ngrok is not required.
- Manual testing without webhook is possible, but it does not validate the real user linking flow.

## Required Accounts And Values

### 1. Telegram Bot Token

Create or reuse a bot through Telegram's BotFather:

1. Open Telegram.
2. Search for `@BotFather`.
3. Send `/newbot` and follow the prompts, or send `/mybots` to manage an existing bot.
4. Copy the bot token.
5. Copy the bot username without the `@` prefix.

Environment values:

```env
TELEGRAM_BOT_TOKEN=123456789:AA...
TELEGRAM_BOT_USERNAME=your_bot_username
```

### 2. Ngrok Authtoken

For local webhook testing:

1. Create or sign in to an ngrok account.
2. Open `https://dashboard.ngrok.com/get-started/your-authtoken`.
3. Copy the authtoken.

Environment value:

```env
NGROK_AUTHTOKEN=your_ngrok_authtoken
```

### 3. Webhook Secret

Generate a local secret:

```bash
openssl rand -hex 32
```

Environment value:

```env
TELEGRAM_WEBHOOK_SECRET=generated_hex_secret
```

The helper script can generate this automatically.

## Local Setup

Run from the repository root:

```bash
TELEGRAM_BOT_TOKEN='botfather_token' \
TELEGRAM_BOT_USERNAME='bot_username_without_at' \
NGROK_AUTHTOKEN='ngrok_authtoken' \
bash scripts/setup_local_telegram_env.sh
```

This creates or updates `.env`. The `.env` file is ignored by git and must not be committed.

Start the full stack with the optional Telegram profile:

```bash
docker compose --profile telegram up -d --build
```

Alternatively, use the setup wrapper:

```bash
./setup.sh --telegram
```

The profile starts:

- `ngrok`: public HTTPS tunnel to `backend:8000`
- `telegram-webhook`: one-off setup container that reads ngrok's public URL and calls Telegram `setWebhook`

Check service status:

```bash
docker compose ps
docker compose logs -f backend worker beat ngrok telegram-webhook
```

Expected worker log:

```text
celery@... ready
```

Expected webhook setup log:

```text
[telegram-webhook] Webhook configured: https://...ngrok.../integrations/telegram/webhook
```

## User Linking Flow

1. Open the frontend at `http://localhost:5173`.
2. Sign in or sign up.
3. Go to the Bulletin page.
4. Click `Connect Telegram`.
5. Telegram opens the bot link with a one-time `/start <token>` payload.
6. Press Start in Telegram.
7. Return to the app and refresh Telegram status.

If successful, the panel shows the linked Telegram username.

## Delivery Test

Generate a Week's Best bulletin from the Bulletin page. If the generated payload is `validated`, the backend creates:

- one in-app notification
- one pending Telegram delivery

The Celery worker sends the PDF and marks the delivery as `sent`.

Database verification:

```bash
docker compose exec postgres psql -U postgres -d academic_platform \
  -c "select id, notification_id, channel, status, attempt_count, last_error, external_message_id from notification_deliveries order by id desc limit 10;"
```

If needed, trigger pending delivery dispatch manually:

```bash
docker compose exec backend celery -A backend.worker.scheduler.app call backend.worker.tasks.dispatch_pending_notification_deliveries --args='[10]'
docker compose logs -f worker
```

## Troubleshooting

- `Telegram integration is not configured.`: `TELEGRAM_BOT_TOKEN` or `TELEGRAM_BOT_USERNAME` is missing.
- Webhook is not called: confirm `telegram-webhook` logged a public HTTPS URL and `getWebhookInfo` has no `last_error_message`.
- User is not linked: the user must open the exact generated `t.me/<bot>?start=<token>` link before the token expires.
- Delivery is `skipped`: no enabled Telegram account exists for the notification user.
- Delivery is `failed`: inspect `last_error`; common causes are invalid bot token, user blocked the bot, or Telegram API/network failure.

## Production Notes

- Do not run ngrok in production.
- Set Telegram webhook to the public backend URL:

```text
https://your-domain.example.com/integrations/telegram/webhook
```

- Keep `TELEGRAM_BOT_TOKEN` and `TELEGRAM_WEBHOOK_SECRET` in secret storage, not in source control.
- The backend validates Telegram webhook requests with `X-Telegram-Bot-Api-Secret-Token`.
