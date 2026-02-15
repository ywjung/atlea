# Multi-stage Docker build for optimized image size and security
# Stage 1: Builder - Install dependencies and prepare application
FROM python:3.11-slim as builder

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    cmake \
    git \
    curl \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /build

# Copy requirements first for better layer caching
COPY requirements.txt .

# Create virtual environment and install dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime - Minimal runtime image
FROM python:3.11-slim

# Set build arguments
ARG DEBIAN_FRONTEND=noninteractive
ARG APP_USER=appuser
ARG APP_UID=1000
ARG APP_GID=1000

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    libpq5 \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user for security
RUN groupadd -g ${APP_GID} ${APP_USER} && \
    useradd -m -u ${APP_UID} -g ${APP_GID} -s /bin/bash ${APP_USER}

# Set working directory
WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY --chown=${APP_USER}:${APP_USER} src/ ./src/
COPY --chown=${APP_USER}:${APP_USER} static/ ./static/
COPY --chown=${APP_USER}:${APP_USER} alembic/ ./alembic/
COPY --chown=${APP_USER}:${APP_USER} alembic.ini ./alembic.ini
COPY --chown=${APP_USER}:${APP_USER} .env.example .env

# Create necessary directories with proper permissions
RUN mkdir -p data model logs backups && \
    chown -R ${APP_USER}:${APP_USER} /app

# Set environment variables
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    HOST=0.0.0.0 \
    PORT=8000

# Switch to non-root user
USER ${APP_USER}

# Expose port (default; override via docker-compose or -e PORT=...)
EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run application (shell form to expand $PORT at runtime)
CMD python -m uvicorn src.web_server:app --host 0.0.0.0 --port ${PORT} --workers 1
