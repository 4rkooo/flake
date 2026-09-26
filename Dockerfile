FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir uv
# dependencies first, from the lock file, so this layer is cached until uv.lock changes
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
# then the code; the second sync only installs the flake package itself (src/ layout)
COPY . .
RUN uv sync --frozen --no-dev
ENTRYPOINT ["uv", "run", "--no-sync", "flake"]
