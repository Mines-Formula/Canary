FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=America/Denver

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Supply the named system zone so localtime-based library logs honor timezone
RUN python -c "from importlib.resources import files; from pathlib import Path; target = Path('/usr/share/zoneinfo/America/Denver'); target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(files('tzdata.zoneinfo').joinpath('America/Denver').read_bytes())"

COPY heartbeat-server/app.py .
COPY emitter/emitter.py .
COPY canary ./canary

# COPY keeps the build context's file mode, which depends on the umask of
# whoever checked the repo out. Normalize it so appuser can read the source.
RUN chmod 0644 app.py emitter.py \
    && chmod -R a+rX canary \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
