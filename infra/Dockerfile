FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY . /app

RUN python - <<'PY'
import pathlib
pathlib.Path('data/uploads').mkdir(parents=True, exist_ok=True)
PY

EXPOSE 8787
CMD ["python", "server.py"]
