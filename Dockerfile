FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir requests
COPY cloud_server.py .
EXPOSE 8765
CMD ["python", "cloud_server.py"]
