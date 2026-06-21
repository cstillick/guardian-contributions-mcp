FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

# Dependencies first (layer cache), then source.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[postgres]"

EXPOSE 8000

# Default: the REST API. Override `command:` for the scheduler or a one-off ingest.
CMD ["guardian-api"]
