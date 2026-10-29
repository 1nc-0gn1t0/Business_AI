FROM python:3.12-slim@sha256:12316debbfb86890f6b2d825820612741ba527ad5a44e3902759141d572bfe8f AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
COPY THIRD_PARTY_NOTICES.txt /licenses/THIRD_PARTY_NOTICES.txt
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && useradd --create-home app \
    && mkdir /var/lib/business-ai-acquisition \
    && chown app:app /var/lib/business-ai-acquisition
COPY app ./app
COPY alembic.ini .
COPY migrations ./migrations
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM base AS integration-tests
USER root
COPY requirements-test-tools.txt ./
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: --no-deps -r requirements-test-tools.txt
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project
COPY tests/integration ./tests/integration
USER app
CMD ["/app/.venv/bin/python", "-m", "pytest", "tests/integration", "-v", "-p", "no:cacheprovider"]

FROM base AS runtime
USER root
# No mount/namespace/terminal administration is needed by the API. Keep shared
# libraries/essential packages: their unresolved advisories remain in the report.
RUN python -m pip uninstall -y pip \
    && apt-get purge -y mount \
    && rm /usr/bin/nsenter /usr/bin/infocmp
USER app
