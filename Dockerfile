# ── Base image ─────────────────────────────────────────────
FROM python:3.12-slim

# ── Set working directory ───────────────────────────────────
WORKDIR /app

# ── Install dependencies ────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy app files ──────────────────────────────────────────
COPY . .

# ── Create data directory for SQLite persistence ────────────
RUN mkdir -p /app/data

# ── Expose port ─────────────────────────────────────────────
EXPOSE 3009

# ── Start the app ───────────────────────────────────────────
CMD ["gunicorn", "--workers", "1", "--bind", "0.0.0.0:3008", "app:app"]
