# Notification System Implementation Plan

Bu doküman, Week's Best bulletin üretimi tamamlandığında kullanıcıya hem uygulama içi bildirim göstermek hem de Telegram üzerinden dokümanı iletmek için uygulanacak teknik planı tanımlar.

## Mevcut Durum

Week's Best üretimi şu an senkron çalışıyor:

```text
Frontend
-> POST /bulletin/weeks-best/generate
-> BulletinSnapshotService.get_or_generate()
-> BulletinSnapshotService.generate()
-> report_snapshots tablosuna payload yazılır
-> payload frontend'e döner
```

İlgili mevcut parçalar:

- `backend/app/api/routes/bulletin.py`
  - `POST /bulletin/weeks-best/generate`
  - `GET /bulletin/weeks-best`
- `backend/app/services/bulletin_snapshot_service.py`
  - `BulletinSnapshotService.generate()`
  - `BulletinSnapshotService._upsert_snapshot()`
- `database/models/ReportSnapshot.py`
  - Week's Best payload'ı `report_snapshots.payload_json` içinde tutuluyor.
- `database/models/UserBulletinPreference.py`
  - `notifications_enabled` alanı var, ama bildirim geçmişi ve kanal teslimat durumu yok.
- `backend/worker/scheduler.py` ve `backend/worker/tasks.py`
  - Celery iskeleti var, gerçek task akışı henüz kurulmamış.

## Hedef Akış

```text
User clicks Generate
-> Backend starts or runs Week's Best generation
-> Snapshot is saved
-> NotificationService creates in-app notification
-> NotificationDelivery is queued for Telegram
-> Celery worker sends Telegram message/document
-> Frontend shows unread notification badge
```

İlk MVP'de endpoint yine senkron payload dönebilir. Telegram gönderimi ve retry mekanizması request dışında Celery task olarak çalışmalıdır.

## Kapsam

MVP kapsamı:

- Week's Best generate tamamlanınca uygulama içi bildirim oluşturma.
- Bildirimleri listeleme, okundu işaretleme ve unread count.
- Kullanıcı Telegram hesabını bot ile bağlama.
- Week's Best dokümanını Telegram'a gönderme.
- Telegram gönderim durumu, hata ve retry kaydı tutma.
- Duplicate bildirim üretimini engelleme.

MVP dışı:

- E-posta bildirimi.
- Push notification.
- Çok kanallı kullanıcı tercih matrisi.
- PDF tasarım üretimi. İlk sürümde Markdown dokümanı yeterli.
- Gerçek production auth hardening. Mevcut `X-User-Id` modeli korunabilir, ama güvenlik notu aşağıda var.

## Veri Modeli

### `notifications`

Kullanıcıya gösterilecek uygulama içi bildirim kaydı.

```text
id                  integer primary key
user_id             integer not null index
type                varchar(60) not null
title               varchar(200) not null
body                text not null
payload_json        jsonb nullable
related_snapshot_key varchar(200) nullable index
read_at             timestamp nullable
created_at          timestamp not null
updated_at          timestamp not null
```

Unique constraint:

```text
uq_notifications_user_type_snapshot(user_id, type, related_snapshot_key)
```

`related_snapshot_key` null olabilecek farklı bildirim türleri ileride gelebilir. Week's Best için her zaman dolu olmalıdır.

Örnek payload:

```json
{
  "snapshot_key": "weeks_best_bulletin:v1:...",
  "selection_type": "cluster",
  "selection_id": "12",
  "selection_label": "Graph Neural Networks",
  "week_start": "2026-06-08",
  "week_end": "2026-06-14",
  "status": "validated",
  "selected_count": 5,
  "document_format": "markdown"
}
```

### `notification_deliveries`

Her bildirim kanalının teslimat durumunu tutar.

```text
id                  integer primary key
notification_id     integer not null index
channel             varchar(30) not null
status              varchar(30) not null
attempt_count       integer not null default 0
next_attempt_at     timestamp nullable
last_error          text nullable
external_message_id varchar(120) nullable
sent_at             timestamp nullable
created_at          timestamp not null
updated_at          timestamp not null
```

`channel` değerleri:

- `in_app`
- `telegram`

`status` değerleri:

- `pending`
- `sent`
- `failed`
- `skipped`

Unique constraint:

```text
uq_notification_delivery_channel(notification_id, channel)
```

### `user_telegram_accounts`

Kullanıcı ile Telegram chat bilgisini bağlar.

```text
id                  integer primary key
user_id             integer not null unique index
telegram_chat_id    varchar(80) not null unique
telegram_user_id    varchar(80) nullable
telegram_username   varchar(120) nullable
is_enabled          boolean not null default true
linked_at           timestamp not null
last_error          text nullable
created_at          timestamp not null
updated_at          timestamp not null
```

### `telegram_link_tokens`

Telegram bot `/start <token>` akışı için kısa ömürlü token tablosu.

```text
id                  integer primary key
user_id             integer not null index
token_hash          varchar(128) not null unique
expires_at          timestamp not null
used_at             timestamp nullable
created_at          timestamp not null
```

Token düz metin DB'ye yazılmamalı. Kullanıcıya verilen token'ın SHA-256 hash'i saklanmalı.

## Alembic Migration

Yeni migration:

```text
database/alembic/versions/<revision>_add_notifications.py
```

Migration şu tabloları oluşturmalı:

- `notifications`
- `notification_deliveries`
- `user_telegram_accounts`
- `telegram_link_tokens`

Indexler:

- `ix_notifications_user_id`
- `ix_notifications_related_snapshot_key`
- `ix_notification_deliveries_notification_id`
- `ix_notification_deliveries_status_next_attempt`
- `ix_user_telegram_accounts_user_id`
- `ix_telegram_link_tokens_user_id`

## Backend Modelleri

Yeni model dosyaları:

```text
database/models/Notification.py
database/models/NotificationDelivery.py
database/models/UserTelegramAccount.py
database/models/TelegramLinkToken.py
```

`database/models/__init__.py` içine import edilmeli. Alembic `Base.metadata` üzerinden modelleri görmeli.

## Backend Servisleri

### `NotificationService`

Dosya:

```text
backend/app/services/notification_service.py
```

Sorumluluklar:

- Uygulama içi bildirim oluşturmak.
- Duplicate kaydı engellemek.
- Delivery kayıtlarını oluşturmak.
- Bildirim listeleme ve okundu işaretleme işlemlerini yapmak.

Önerilen metotlar:

```python
class NotificationService:
    def create_weeks_best_generated(
        self,
        user_id: int,
        bulletin_payload: dict,
        enable_telegram: bool = True,
    ) -> Notification:
        ...

    def list_notifications(self, user_id: int, limit: int, unread_only: bool) -> dict:
        ...

    def unread_count(self, user_id: int) -> int:
        ...

    def mark_read(self, user_id: int, notification_id: int) -> dict:
        ...

    def mark_all_read(self, user_id: int) -> dict:
        ...
```

Week's Best için bildirim sadece şu durumlarda oluşturulmalı:

- `payload["status"] == "validated"`
- `payload["snapshot_key"]` mevcut
- Kullanıcının bulletin notification tercihi açıksa

`status == "empty"` için uygulama içi düşük öncelikli bilgi bildirimi opsiyonel olabilir. MVP'de göndermemek daha sade.

### `TelegramLinkService`

Dosya:

```text
backend/app/services/telegram_link_service.py
```

Sorumluluklar:

- Kullanıcı için tek kullanımlık link token üretmek.
- `/start <token>` ile gelen Telegram chat bilgisini kullanıcıya bağlamak.
- Telegram bağlantısını kaldırmak veya pasifleştirmek.

Önerilen metotlar:

```python
class TelegramLinkService:
    def create_link_token(self, user_id: int) -> dict:
        ...

    def consume_start_token(self, token: str, telegram_update: dict) -> dict:
        ...

    def get_status(self, user_id: int) -> dict:
        ...

    def unlink(self, user_id: int) -> None:
        ...
```

### `TelegramBotService`

Dosya:

```text
backend/app/services/telegram_bot_service.py
```

Sorumluluklar:

- Telegram Bot API çağrılarını izole etmek.
- `sendMessage` ile kısa özet göndermek.
- `sendDocument` ile Markdown dokümanı göndermek.
- API hatalarını normalize etmek.

Resmi API:

- `sendMessage`: `https://core.telegram.org/bots/api#sendmessage`
- `sendDocument`: `https://core.telegram.org/bots/api#senddocument`
- `setWebhook`: `https://core.telegram.org/bots/api#setwebhook`

İlk sürümde `httpx` kullanılabilir. `backend/requirements.txt` içinde yoksa eklenmeli.

Telegram mesaj formatı:

```text
Week's Best ready: {selection_label}
Period: {week_start} - {week_end}
Selected papers: {selected_count}

The full bulletin is attached as Markdown.
```

Tam içerik:

```text
filename: weeks_best_{selection_type}_{selection_id}_{week_start}_{week_end}.md
content: bulletin_payload["full_markdown"]
```

Telegram doküman gönderimi 50 MB sınırına sahiptir. Markdown bulletin bunun çok altında kalır.

## API Tasarımı

### Notification Routes

Yeni dosya:

```text
backend/app/api/routes/notifications.py
```

Router `backend/app/main.py` içine eklenmeli.

Endpointler:

```text
GET /notifications
GET /notifications/unread-count
PATCH /notifications/{notification_id}/read
POST /notifications/read-all
```

Örnek response:

```json
{
  "items": [
    {
      "id": 14,
      "type": "weeks_best_generated",
      "title": "Week's Best is ready",
      "body": "Graph Neural Networks bulletin for 2026-06-08 - 2026-06-14 is ready.",
      "payload": {
        "snapshot_key": "weeks_best_bulletin:v1:...",
        "selection_type": "cluster",
        "selection_id": "12",
        "week_start": "2026-06-08",
        "week_end": "2026-06-14"
      },
      "read_at": null,
      "created_at": "2026-06-20T10:30:00"
    }
  ],
  "unread_count": 1
}
```

### Telegram Routes

Yeni dosya:

```text
backend/app/api/routes/telegram.py
```

Endpointler:

```text
GET /telegram/status
POST /telegram/link-token
DELETE /telegram/link
POST /integrations/telegram/webhook
```

`POST /telegram/link-token` response:

```json
{
  "bot_username": "academic_platform_bot",
  "link_url": "https://t.me/academic_platform_bot?start=<token>",
  "expires_at": "2026-06-20T11:00:00"
}
```

Webhook güvenliği:

- Telegram `setWebhook` sırasında `secret_token` kullanılmalı.
- Webhook endpoint'i `X-Telegram-Bot-Api-Secret-Token` header değerini `settings.TELEGRAM_WEBHOOK_SECRET` ile karşılaştırmalı.
- Secret yanlışsa `403` dönmeli.

### Week's Best Generate Route Değişikliği

Mevcut:

```python
@router.post("/bulletin/weeks-best/generate")
def generate_weeks_best_bulletin(payload: WeeksBestBulletinRequest, db: Session = Depends(get_db)):
    return BulletinSnapshotService(db).get_or_generate(...)
```

Önerilen:

```python
@router.post("/bulletin/weeks-best/generate")
def generate_weeks_best_bulletin(
    payload: WeeksBestBulletinRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bulletin = BulletinSnapshotService(db).get_or_generate(...)
    NotificationService(db).create_weeks_best_generated(
        user_id=user.id,
        bulletin_payload=bulletin,
        enable_telegram=True,
    )
    return bulletin
```

Bu değişiklik için frontend request header'ına `getAuthHeaders()` eklenmeli.

## Celery Task Tasarımı

Mevcut Celery iskeleti kullanılacak:

```text
backend/worker/scheduler.py
backend/worker/tasks.py
```

Yeni tasklar:

```python
@app.task(bind=True, max_retries=3)
def dispatch_notification_delivery(self, delivery_id: int):
    ...

@app.task
def generate_weeks_best_for_user(user_id: int, selection_type: str, selection_id: str, week_start: str, week_end: str):
    ...

@app.task
def generate_weekly_bulletins_for_all_users():
    ...
```

MVP için zorunlu task:

- `dispatch_notification_delivery`

Bu task:

1. `notification_deliveries` kaydını alır.
2. `channel == "telegram"` ise kullanıcının `user_telegram_accounts` kaydını kontrol eder.
3. Telegram bağlantısı yoksa `skipped` yazar.
4. Bağlantı varsa önce kısa mesaj, sonra Markdown dokümanı gönderir.
5. Başarılıysa `sent`, `sent_at`, `external_message_id` yazar.
6. Hata varsa `attempt_count`, `last_error`, `next_attempt_at` günceller.
7. Retry limiti dolduysa `failed` yazar.

Retry politikası:

```text
1. hata: 1 dakika sonra
2. hata: 5 dakika sonra
3. hata: 30 dakika sonra
sonrası: failed
```

## Docker Compose Değişiklikleri

Mevcut `docker-compose.yml` içinde Redis yok. Celery broker olarak Redis kullanıyor. Compose'a eklenmeli:

```yaml
redis:
  image: redis:7-alpine
  ports:
    - "6379:6379"
  restart: unless-stopped
```

Backend env:

```text
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0
TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
TELEGRAM_BOT_USERNAME=${TELEGRAM_BOT_USERNAME}
TELEGRAM_WEBHOOK_SECRET=${TELEGRAM_WEBHOOK_SECRET}
PUBLIC_APP_URL=${PUBLIC_APP_URL}
```

Worker service:

```yaml
worker:
  build:
    context: .
    dockerfile: backend/Dockerfile
  command: celery -A backend.worker.scheduler.app worker --loglevel=info
  env_file:
    - path: .env
      required: false
  depends_on:
    - postgres
    - redis
```

İleride haftalık otomatik üretim için `celery beat` ayrı service olarak eklenebilir.

## Settings Değişiklikleri

`backend/app/core/config.py` içine:

```python
CELERY_BROKER_URL: str = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
TELEGRAM_BOT_TOKEN: str | None = None
TELEGRAM_BOT_USERNAME: str | None = None
TELEGRAM_WEBHOOK_SECRET: str | None = None
PUBLIC_APP_URL: str = "http://localhost:5173"
TELEGRAM_LINK_TOKEN_TTL_MINUTES: int = 30
```

`backend/worker/scheduler.py` hard-coded Redis URL yerine settings kullanmalı.

## Frontend Değişiklikleri

### API çağrısı

`frontend/src/pages/BulletinPage.tsx` içinde Week's Best generate request'i:

```ts
headers: {
  'Content-Type': 'application/json',
  ...getAuthHeaders(),
}
```

### Notification UI

Önerilen yeni componentler:

```text
frontend/src/components/NotificationBell.tsx
frontend/src/components/NotificationPanel.tsx
frontend/src/api/notifications.ts
frontend/src/api/telegram.ts
```

`Layout` veya `Sidebar` içinde:

- unread count badge
- son bildirimler paneli
- "Mark all read"
- Week's Best bildirimi tıklanınca bulletin sayfasına ilgili query ile gitme

Örnek route:

```text
/bulletin?weeks_best_snapshot_key=<snapshot_key>
```

Alternatif olarak payload içindeki seçim bilgisi ile mevcut `GET /bulletin/weeks-best` çağrısı yapılabilir:

```text
/bulletin?selection_type=cluster&selection_id=12&week_start=2026-06-08&week_end=2026-06-14
```

### Telegram Settings UI

Bulletin preference paneline veya Settings sayfasına:

- Telegram bağlantı durumu
- "Connect Telegram" butonu
- "Disconnect" butonu
- hata mesajı

Connect akışı:

1. Frontend `POST /telegram/link-token` çağırır.
2. Dönen `link_url` yeni sekmede açılır.
3. Kullanıcı botta `/start <token>` akışını tamamlar.
4. Frontend polling ile `GET /telegram/status` çağırıp bağlantı durumunu yeniler.

## Haftalık Otomatik Üretim

İkinci fazda Celery Beat ile otomatik üretim eklenmeli.

Task:

```python
generate_weekly_bulletins_for_all_users()
```

Davranış:

1. `notifications_enabled == true` olan `UserBulletinPreference` kayıtlarını alır.
2. `notification_frequency == "weekly"` olanları filtreler.
3. Önceki hafta aralığını `default_previous_week()` ile hesaplar.
4. Kullanıcının seçimine göre cluster/category bazlı Week's Best üretir.
5. Her üretim sonunda `NotificationService.create_weeks_best_generated()` çağırır.

Önemli not: Mevcut kullanıcı tercihi `selection_type == "clusters"` veya `"categories"` şeklinde çoklu seçim tutuyor. Week's Best servisi ise tek `cluster` veya tek `category` bekliyor. Otomatik üretim için iki seçenek var:

1. Her seçilen cluster/category için ayrı Week's Best üret.
2. Kullanıcı tercihlerinden tek birleşik "personal weekly bulletin" üretmek için ayrı servis tasarla.

MVP için 1. seçenek daha az riskli.

## Güvenlik Notları

Mevcut auth modeli frontend localStorage'daki kullanıcı ID'sini `X-User-Id` header olarak gönderiyor. Backend bu header'a güveniyor. Bildirim ve Telegram bağlantısı kişisel veri içerdiği için production öncesi şu iyileştirmeler gerekli:

- JWT veya server-side session.
- Password hashing için bcrypt/Argon2.
- Telegram link token için kısa TTL ve hash storage.
- Webhook secret doğrulaması.
- Telegram bot token'ın sadece env üzerinden verilmesi.
- Bildirim endpoint'lerinde her zaman `notification.user_id == current_user.id` kontrolü.

## Hata Yönetimi

Telegram hataları kullanıcıya doğrudan Week's Best generate hatası olarak dönmemeli. Generate başarılıysa kullanıcı dokümanı uygulama içinde görebilmeli.

Önerilen davranış:

- Snapshot üretimi başarısızsa mevcut API hata döner.
- Snapshot üretimi başarılı ama Telegram gönderimi başarısızsa:
  - in-app notification yine oluşturulur.
  - delivery `failed` veya retry pending olur.
  - frontend Telegram durumunda son hata gösterilebilir.

## Test Planı

Backend unit testleri:

- `NotificationService.create_weeks_best_generated()` validated payload ile kayıt oluşturur.
- Aynı `snapshot_key` ikinci kez gelirse duplicate oluşturmaz.
- `status != validated` için notification oluşturmaz.
- Telegram hesabı yoksa delivery `skipped` olur.
- Telegram API mock başarılıysa delivery `sent` olur.
- Telegram API mock hata verirse retry alanları güncellenir.
- Kullanıcı başka kullanıcının notification kaydını read yapamaz.

API testleri:

- `GET /notifications` auth yokken 401 döner.
- `GET /notifications` sadece current user kayıtlarını döner.
- `PATCH /notifications/{id}/read` read_at set eder.
- `POST /telegram/link-token` token üretir.
- `POST /integrations/telegram/webhook` secret yanlışsa 403 döner.
- `/start <token>` geçerliyse Telegram hesabı bağlanır.

Frontend test/smoke:

- Week's Best generate request'i `X-User-Id` header gönderir.
- Notification badge unread count gösterir.
- Bildirim tıklanınca Week's Best içeriğine yönlenir.
- Telegram connect flow link üretir ve status yeniler.

Manual test:

```bash
# Migrations
alembic -c database/alembic.ini upgrade head

# Backend
uvicorn backend.app.main:app --reload

# Worker
celery -A backend.worker.scheduler.app worker --loglevel=info

# Frontend
cd frontend && npm run dev
```

Telegram webhook local test için ngrok/cloudflared gibi HTTPS tünel gerekir. Production'da `PUBLIC_APP_URL` doğrudan HTTPS olmalı.

## Uygulama Sırası

### Faz 1: In-app Notification

1. DB migration ekle.
2. SQLAlchemy modellerini ekle.
3. `NotificationService` yaz.
4. `/notifications` endpointlerini ekle.
5. Week's Best generate endpoint'inde notification oluştur.
6. Frontend notification badge/panel ekle.
7. Unit/API testlerini ekle.

### Faz 2: Telegram Linkleme

1. Settings/env alanlarını ekle.
2. `TelegramLinkService` yaz.
3. Telegram route ve webhook endpointini ekle.
4. Frontend Telegram connect UI ekle.
5. Webhook secret ve token TTL testlerini ekle.

### Faz 3: Telegram Delivery

1. `TelegramBotService` yaz.
2. `notification_deliveries` task'ını Celery ile çalıştır.
3. Docker Compose'a Redis ve worker ekle.
4. Markdown doküman gönderimini ekle.
5. Retry ve failed durumlarını test et.

### Faz 4: Otomatik Haftalık Üretim

1. Celery Beat ekle.
2. `generate_weekly_bulletins_for_all_users()` task'ını yaz.
3. Kullanıcı tercihinden cluster/category jobları üret.
4. Duplicate snapshot/notification kontrollerini doğrula.

## Kabul Kriterleri

- Kullanıcı Week's Best generate ettiğinde bildirim listesinde yeni kayıt görür.
- Aynı snapshot tekrar generate edilirse duplicate notification oluşmaz.
- Bildirim unread badge'e yansır.
- Kullanıcı bildirimi okundu işaretleyebilir.
- Telegram bağlı değilse sistem hata vermeden in-app notification üretir.
- Telegram bağlıysa kullanıcı kısa mesaj ve Markdown dokümanı alır.
- Telegram gönderim hataları retry edilir ve DB'de izlenebilir.
- Telegram webhook secret doğrulaması vardır.
- Worker kapalıyken generate akışı bozulmaz; delivery pending kalır.
- Worker açıldığında pending delivery kayıtları gönderilir.

## Riskler ve Çözümler

| Risk | Etki | Çözüm |
| --- | --- | --- |
| Request içinde Telegram çağrısı yapılırsa generate yavaşlar veya fail olur | Kullanıcı deneyimi bozulur | Telegram delivery her zaman Celery task |
| Duplicate notification | Kullanıcı spam alır | `user_id + type + snapshot_key` unique constraint |
| Telegram bot kullanıcıya yazamaz | Delivery fail olur | Kullanıcı önce botu `/start` ile başlatmalı |
| Webhook sahte çağrı alır | Güvenlik açığı | `X-Telegram-Bot-Api-Secret-Token` doğrulaması |
| Mevcut auth zayıf | Kullanıcı impersonation riski | MVP notu; production öncesi JWT/session |
| Worker down | Telegram gitmez | Delivery pending kalır, worker açılınca devam |
| Markdown çok uzun | Telegram text limiti aşılır | Tam içerik `sendDocument`, mesaj kısa caption |

## Sonraki İyileştirmeler

- PDF render ve Telegram'a PDF gönderimi.
- Bildirim tercihleri: in-app açık/kapalı, Telegram açık/kapalı.
- Admin ekranında delivery failure monitoring.
- Prometheus metricleri:
  - `notifications_created_total`
  - `telegram_deliveries_sent_total`
  - `telegram_deliveries_failed_total`
  - `notification_delivery_latency_seconds`
- WebSocket veya Server-Sent Events ile real-time notification badge.
- Kullanıcıya "test Telegram message" butonu.
