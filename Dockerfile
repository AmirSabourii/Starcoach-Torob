FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    DATABASE_PATH=/data/torob.sqlite \
    DATA_DIR=/data \
    BOXAPI_BASE_URL=https://ai.boxapi.ir/ai/v1 \
    BOXAPI_MODEL=gpt-6-luna \
    PORT=8000

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY scripts ./scripts

RUN mkdir -p /data

EXPOSE 8000

# The dataset, sqlite file and embedding cache are not baked into the image.
# Mount a disk at /data, then run scripts/build_db.py and optionally scripts/embed_products.py.
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
