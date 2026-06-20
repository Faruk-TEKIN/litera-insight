FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install CPU-only torch first to save image space and build time
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

# Copy requirements and install python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend, AI helper, and database code
COPY backend /app/backend
COPY ai_engine /app/ai_engine
COPY database /app/database
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Set Python path so backend can be imported correctly
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Bootstrap database/migrations, then run the application
ENTRYPOINT ["/app/docker-entrypoint.sh"]
