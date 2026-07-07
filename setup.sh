#!/bin/bash
set -e

echo "=== YTU-CE Akademik Yayın İstihbarat ve Analiz Platformu Oto Kurulum ==="

# 1. Ortam degiskenlerini kopyala / guncelle
if [ ! -f .env ]; then
    echo "[1/8] Creating .env from .env.example..."
    cp .env.example .env
else
    echo "[1/8] .env already exists, checking settings..."
    # Eğer eski .env varsa, docker container ismini localhost ile değiştirerek host uyumluluğunu sağla
    if grep -q "@postgres:5432" .env; then
        echo "Updating DATABASE_URL to localhost:5432 for host compatibility..."
        sed -i 's|@postgres:5432|@localhost:5432|g' .env
    fi
    if grep -q "//redis:6379" .env; then
        echo "Updating CELERY URLs to localhost:6379 for host compatibility..."
        sed -i 's|//redis:6379|//localhost:6379|g' .env
    fi
    if grep -q "OLLAMA_BASE_URL=http://host.docker.internal" .env; then
        echo "Updating OLLAMA_BASE_URL to localhost:11434..."
        sed -i 's|OLLAMA_BASE_URL=http://host.docker.internal:11434|OLLAMA_BASE_URL=http://localhost:11434|g' .env
    fi
fi

# 2. Virtual environment olustur
if [ ! -d .venv ]; then
    echo "[2/8] Creating virtual environment (.venv)..."
    python3 -m venv .venv
else
    echo "[2/8] Virtual environment (.venv) already exists."
fi

# 3. Bağımlılıkları yükle
echo "[3/8] Installing/upgrading dependencies..."
.venv/bin/pip install --upgrade pip setuptools wheel
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install -r backend/requirements.txt

# 4. Çıktı dizinini oluştur
echo "[4/8] Preparing exports directory..."
mkdir -p exports/retrieval

# 5. Docker stack'i başlat
echo "[5/8] Starting Docker Compose containers..."
docker compose up -d --build

# 6. Veritabanının hazır olmasını bekle
echo "[6/8] Waiting for PostgreSQL to be ready..."
until docker compose exec postgres pg_isready -U postgres >/dev/null 2>&1; do
    echo -n "."
    sleep 1
done
echo " PostgreSQL is ready!"

# 7. Migrasyonların backend tarafından uygulanmasını bekle
echo "[7/8] Waiting for database migrations to complete..."
max_attempts=30
attempt=0
until [ $attempt -ge $max_attempts ] || (docker compose exec postgres psql -U postgres -d academic_platform -c "SELECT to_regclass('public.articles');" 2>/dev/null | grep -q "articles"); do
    echo -n "."
    sleep 2
    attempt=$((attempt+1))
done

if [ $attempt -eq $max_attempts ]; then
    echo " Warning: migrations check timed out. Proceeding anyway..."
else
    echo " Migrations applied successfully!"
fi

# 8. Veri çekme ve analiz adımlarını çalıştır
echo "[8/8] Seeding database and running analysis pipeline..."

echo "1. Running run_bulk_ingest.py..."
.venv/bin/python run_bulk_ingest.py --max-results 4000 --sources arxiv

echo "2. Generating and saving embeddings..."
.venv/bin/python ai_engine/embeddings/embeddings_to_db.py --total-articles 4000 --batch-size 250

echo "3. Building BM25 index..."
.venv/bin/python scripts/build_bm25_index.py

echo "4. Running topic clustering..."
.venv/bin/python ai_engine/clustering/ClusterFunctions.py --max-articles 4000

echo "=== Kurulum Başarıyla Tamamlandı! ==="
