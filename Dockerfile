FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py .
RUN mkdir -p /app/audio_cache
ENV PORT=8001
ENV AUDIO_DIR=/app/audio_cache
EXPOSE 8001
CMD ["python", "server.py"]
