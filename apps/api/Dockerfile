FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app/apps/api

RUN pip install --no-cache-dir uv

COPY apps/api/pyproject.toml ./pyproject.toml
RUN uv sync --no-dev

COPY apps/api .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
