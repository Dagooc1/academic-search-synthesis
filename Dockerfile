FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

EXPOSE $PORT

CMD ["gunicorn", "--bind", "0.0.0.0:$PORT", "app:app"]