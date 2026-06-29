FROM python:3.11-slim

WORKDIR /app

# Install build dependencies for uvicorn[standard] (uvloop, httptools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN mkdir -p backend/uploads

EXPOSE 8000

ENV ADMIN_PASSWORD=***
ENV PORT=8000

CMD ["python", "backend/main.py"]
