FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY heartbeat-server/app.py .
COPY emitter/emitter.py .

# COPY keeps the build context's file mode, which depends on the umask of
# whoever checked the repo out. Normalize it so appuser can read the source.
RUN chmod 0644 app.py emitter.py

RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
