FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-21-jre-headless \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data/source-worlds /app/data/bluemap/config /app/data/bluemap/web /app/data/tmp /app/bin

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
