# Oto Kurulum Adımları

Bu repo için teslim akışı Docker Compose'tur. Model dahil tüm servisler konteyner içinde çalışır.

## Beklenen Akış

```bash
cp .env.example .env
docker compose down --remove-orphans
docker compose up -d --build
```

## Ne Olur

- PostgreSQL dump yoksa boş veritabanı ile başlar.
- `pgvector` extension PostgreSQL init sırasında etkinleşir.
- `ollama-pull` modeli indirir ve ısıtır.
- Backend migration'ları uygular ve cache snapshot'larını yeniler.
- Backend ve worker aynı in-network `ollama` servisini kullanır.
- RAG teslim profili için reranker kapalı gelir.

## Doğrulama

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/ready
docker compose logs -f ollama-pull backend frontend
```

## Opsiyonel Yeniden Kurulum

Eğer stack'i tamamen temizleyip yeniden kurmak isterseniz:

```bash
docker compose down --remove-orphans
docker compose up -d --build --force-recreate
```
