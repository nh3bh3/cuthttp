# Multi-stage Dockerfile for chfs-py
# Supports both development and production builds

ARG PYTHON_VERSION=3.11
ARG ALPINE_VERSION=3.18

# Base image with Python
FROM python:${PYTHON_VERSION}-alpine${ALPINE_VERSION} AS base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    libffi-dev \
    openssl-dev \
    && rm -rf /var/cache/apk/*

# Create app user
RUN addgroup -g 1000 chfs && \
    adduser -u 1000 -G chfs -s /bin/sh -D chfs

# Set work directory
WORKDIR /app

# Copy requirements first for better caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

# Development stage
FROM base AS development

# Install development dependencies
RUN pip install --no-cache-dir pytest pytest-asyncio httpx pytest-cov

# Copy application code
COPY --chown=chfs:chfs . .

# Switch to app user
USER chfs

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/healthz', timeout=5)"

# Default command
CMD ["python", "-m", "app.main", "--config", "chfs.yaml"]

# Production stage
FROM base AS production

# Copy only necessary files
COPY --chown=chfs:chfs app/ ./app/
COPY --chown=chfs:chfs templates/ ./templates/
COPY --chown=chfs:chfs static/ ./static/
COPY --chown=chfs:chfs chfs.yaml ./

# Create directories for data and logs
RUN mkdir -p /data /app/logs && \
    chown -R chfs:chfs /data /app/logs

# Switch to app user
USER chfs

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/healthz', timeout=5)" || exit 1

# Volume for data
VOLUME ["/data"]

# Default command with production settings
CMD ["python", "-m", "app.main", "--config", "chfs.yaml"]

# Build stage for creating distributable image
FROM production AS dist

# Copy everything needed for distribution
COPY --chown=chfs:chfs . .

# Set labels
LABEL maintainer="chfs-py team" \
      description="Lightweight file server with WebDAV support" \
      version="1.0.0" \
      org.opencontainers.image.title="chfs-py" \
      org.opencontainers.image.description="Lightweight file server similar to CuteHttpFileServer/chfs" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.vendor="chfs-py" \
      org.opencontainers.image.licenses="MIT"
