# Oto Kurulum Adımları

Bu repo için teslim akışı Docker Compose'tur. Model dahil tüm servisler konteyner içinde çalışır.

## Beklenen Akış

```bash
cp .env.example .env
./setup.sh
```

## Ne Olur

- PostgreSQL dump yoksa boş veritabanı ile başlar.
- `pgvector` extension PostgreSQL init sırasında etkinleşir.
- `ollama-pull` modeli indirir ve ısıtır.
- Backend migration'ları uygular ve cache snapshot'larını yeniler.
- Backend ve worker aynı in-network `ollama` servisini kullanır.
- RAG teslim profili için reranker kapalı gelir.

## İlk Kurulumda Veri Yükleme

Eğer dump kullanmıyorsanız ve demo veri setini de yüklemek istiyorsanız:

```bash
./setup.sh --seed
```

Bu mod container içinde şu bir defalık işleri çalıştırır:

- `run_bulk_ingest.py`
- `ai_engine/embeddings/embeddings_to_db.py`
- `scripts/build_bm25_index.py`
- `ai_engine/clustering/ClusterFunctions.py`
- `ReportSnapshotService.refresh_default_snapshots()`

Aynı adımlar elle çalıştırılmak istenirse komut dizisi şöyledir:

```bash
docker compose run --rm --no-deps --entrypoint python backend /app/run_bulk_ingest.py --max-results 4000 --sources arxiv,openalex
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250
docker compose run --rm --no-deps --entrypoint python backend /app/scripts/build_bm25_index.py
docker compose run --rm --no-deps --entrypoint python backend /app/ai_engine/clustering/ClusterFunctions.py --max-articles 4000 --include-openalex
docker compose run --rm --no-deps --entrypoint python backend -c "from database.db import SessionLocal; from backend.app.services.report_snapshot_service import ReportSnapshotService; db=SessionLocal(); print(ReportSnapshotService(db).refresh_default_snapshots()); db.close()"
```

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
