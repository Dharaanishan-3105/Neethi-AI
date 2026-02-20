# Use Python 3.11 slim image for faster builds
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements-optimized.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements-optimized.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 10000

# Set environment variables
ENV FLASK_ENV=production
ENV PORT=10000

# Start the application
CMD ["python", "neethi.py"]
