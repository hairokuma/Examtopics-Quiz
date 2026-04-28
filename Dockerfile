FROM python:3.12-slim

WORKDIR /app

# Copy requirements first for better caching
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .


EXPOSE 5000
CMD ["python", "app.py"]
