# --- UI build ---
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # tsc -b && vite build -> /ui/dist

# --- App ---
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
# dependencies first, from the lock file, so this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# then the code; the second sync only installs the flake package itself (src/ layout)
COPY . .
RUN uv sync --frozen --no-dev
# UI last, so it doesn't invalidate the Python dependency layers above
COPY --from=ui /ui/dist ./frontend/dist
ENV FLAKE_DEMO_FAKE=1 FLAKE_DEMO_PACE=1.0 PORT=8000
EXPOSE 8000
# --ui is explicit: create_app's REPO-relative default only resolves correctly because the
# project is installed editable by uv sync; passing it directly removes that assumption
CMD ["uv", "run", "--no-sync", "flake-demo", "--fake", "--host", "0.0.0.0", "--ui", "/app/frontend/dist"]
