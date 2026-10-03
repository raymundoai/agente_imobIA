FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml alembic.ini ./
COPY alembic ./alembic
COPY app ./app
RUN pip install --no-cache-dir .

# --proxy-headers takes the client IP from the reverse proxy (needed by the login limits);
# set FORWARDED_ALLOW_IPS to the proxy address, or "*" when the port is not public.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
