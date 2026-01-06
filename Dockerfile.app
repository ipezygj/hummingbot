# Multi-stage Dockerfile for Hummingbot App
# Builds both the web frontend and Python backend into a single image

# =============================================================================
# Stage 1: Build the web frontend
# =============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app

# Copy package files
COPY hummingbot-app/package.json hummingbot-app/pnpm-lock.yaml* hummingbot-app/package-lock.json* ./

# Install dependencies
RUN if [ -f pnpm-lock.yaml ]; then \
        npm install -g pnpm && pnpm install --frozen-lockfile; \
    else \
        npm ci; \
    fi

# Copy source files
COPY hummingbot-app/ ./

# Build the frontend
RUN npm run build

# =============================================================================
# Stage 2: Build the final image with Python backend + static frontend
# =============================================================================
FROM python:3.10-slim-bullseye

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /hummingbot

# Copy requirements first for better caching
COPY setup.py setup.cfg pyproject.toml ./
COPY hummingbot/ ./hummingbot/
COPY bin/ ./bin/
COPY scripts/ ./scripts/
COPY conf/ ./conf/

# Install Python dependencies
RUN pip install --upgrade pip setuptools wheel && \
    pip install uvicorn fastapi aiofiles && \
    pip install -e .

# Copy the built frontend from stage 1
COPY --from=frontend-builder /app/dist /hummingbot/hummingbot-app/dist

# Create a script to serve static files from FastAPI
RUN cat > /hummingbot/hummingbot/api/static.py << 'EOF'
"""
Static file serving for the embedded web app
"""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = Path("/hummingbot/hummingbot-app/dist")

def mount_static_files(app: FastAPI):
    """Mount static files if the dist directory exists"""
    if STATIC_DIR.exists():
        # Serve static assets
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        # Serve index.html for SPA routing
        @app.get("/")
        @app.get("/{path:path}")
        async def serve_spa(path: str = ""):
            # If requesting an API route, let it pass through
            if path.startswith("api/"):
                return None
            # Serve index.html for all other routes (SPA)
            index_file = STATIC_DIR / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return {"error": "Frontend not found"}
EOF

# Update the FastAPI app to serve static files
RUN cat > /hummingbot/hummingbot/api/app_with_static.py << 'EOF'
"""
FastAPI Application with Static File Serving
"""
from hummingbot.api.app import create_app as create_api_app
from hummingbot.api.static import mount_static_files, STATIC_DIR

def create_app():
    """Create FastAPI app with static file serving"""
    app = create_api_app()

    # Mount static files if available
    if STATIC_DIR.exists():
        mount_static_files(app)

    return app
EOF

# Create default config with API enabled
RUN mkdir -p /hummingbot/conf && \
    cat > /hummingbot/conf/conf_client.yml << 'EOF'
# Hummingbot App Docker Configuration
instance_id: hummingbot-docker

api:
  api_enabled: true
  api_host: "0.0.0.0"
  api_port: 8000

mqtt_bridge:
  mqtt_autostart: false

logging:
  log_level: INFO
EOF

# Create entrypoint script
RUN cat > /hummingbot/docker-entrypoint.sh << 'EOF'
#!/bin/bash
set -e

echo "========================================="
echo "     Hummingbot App Docker Container     "
echo "========================================="
echo ""
echo "Starting Hummingbot in headless mode..."
echo "API will be available at http://localhost:8000"
echo "Web UI will be available at http://localhost:8000"
echo "API docs at http://localhost:8000/docs"
echo ""

# Start hummingbot in headless mode
exec python bin/hummingbot_quickstart.py --headless "$@"
EOF

RUN chmod +x /hummingbot/docker-entrypoint.sh

# Expose the API port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Set the entrypoint
ENTRYPOINT ["/hummingbot/docker-entrypoint.sh"]
