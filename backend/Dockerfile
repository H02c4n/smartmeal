# Development image (includes dev dependencies). A production image is a separate, later task.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN pip install --no-cache-dir uv==0.11.7

# Non-root user. UID/GID can be overridden to match the host user (bind-mounted source).
ARG UID=1000
ARG GID=1000
RUN groupadd --gid $GID app && useradd --uid $UID --gid $GID --create-home app \
    && mkdir -p /opt/venv /app && chown -R app:app /opt/venv /app

USER app
WORKDIR /app

# Dependencies first so this layer is cached until the lockfile changes.
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen

COPY --chown=app:app . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
