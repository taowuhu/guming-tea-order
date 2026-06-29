FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create uploads directory
RUN mkdir -p backend/uploads

# Data directory for SQLite persistence
VOLUME ["/app/backend"]

EXPOSE 8000

ENV ADMIN_PASSWORD=guming2024
ENV PORT=8000

CMD ["python", "backend/main.py"]
