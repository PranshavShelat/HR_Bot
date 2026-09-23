# HR agent (bot.py): interactive LangGraph CLI.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root user. /data holds the SQLite database (a named volume in compose);
# creating it here gives a fresh volume the right owner.
RUN useradd --create-home --uid 1000 hrbot \
    && mkdir /data && chown hrbot:hrbot /data

WORKDIR /app

# Dependencies first: this layer is reused until requirements.txt changes.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Source last: editing bot.py only rebuilds this small layer.
COPY --chown=hrbot:hrbot bot.py .

USER hrbot
ENV DB_PATH=/data/hr_database.db
ENTRYPOINT ["python", "bot.py"]
