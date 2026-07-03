FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# PORT is read by main.py at runtime (see `if __name__ == "__main__"` block);
# 5000 matches the port used by docker-compose for local dev.
ENV PORT=5000
EXPOSE 5000

# Default command runs the API. Fly.io overrides this per process group
# (see fly.toml) so the same image also runs the Celery worker.
CMD ["python", "main.py"]
