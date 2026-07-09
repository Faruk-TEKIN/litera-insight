# Optional Telegram PDF Notifications

Telegram notifications are optional. The app works normally without them.

Enable this feature when users want Week's Best PDF bulletins delivered directly to their phone through Telegram. The app still creates in-app notifications; Telegram adds mobile delivery for the generated PDF report.

## Quick Setup

You need three values:

- `TELEGRAM_BOT_TOKEN`: create a bot in Telegram with `@BotFather`, then copy the token.
- `TELEGRAM_BOT_USERNAME`: the same bot username, without `@`.
- `NGROK_AUTHTOKEN`: copy it from `https://dashboard.ngrok.com/get-started/your-authtoken`.

Run from the repository root:

```bash
TELEGRAM_BOT_TOKEN='botfather_token' \
TELEGRAM_BOT_USERNAME='bot_username_without_at' \
NGROK_AUTHTOKEN='ngrok_authtoken' \
bash scripts/setup_local_telegram_env.sh
```

Then start the optional Telegram profile:

```bash
./setup.sh --telegram
```

This starts ngrok, configures the Telegram webhook automatically, and keeps all secrets in local `.env` only.

## User Flow

1. Open the Bulletin page.
2. Click `Connect Telegram`.
3. Telegram opens the bot link.
4. Press `Start`.
5. Generate a Week's Best bulletin.

If the bulletin is validated, the user receives the PDF in Telegram.

## Notes

- Local webhook testing needs ngrok because Telegram cannot reach `localhost`.
- Production does not need ngrok; use the public HTTPS backend URL instead.
- Never commit `.env`, bot tokens, webhook secrets, or ngrok tokens.
- If delivery fails, check `notification_deliveries.last_error` and worker logs.
