FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home app
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS integration-tests
USER root
RUN pip install --no-cache-dir uv==0.13.1
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY tests/integration ./tests/integration
USER app
CMD ["/app/.venv/bin/python", "-m", "pytest", "tests/integration", "-v", "-p", "no:cacheprovider"]

FROM base AS runtime
