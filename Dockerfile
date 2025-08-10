FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY main.py .
COPY config.sample.json .

# Create directories
RUN mkdir -p /app/config /youtube

# Set permissions
RUN chown -R 1000:1000 /app

# Switch to non-root user
USER 1000:1000

EXPOSE 8001

CMD ["python", "main.py", "--server"]
