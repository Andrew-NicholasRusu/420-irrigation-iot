# Build context is ./local (see docker-compose.yml) so common/db.py can be copied in.
FROM python:3.12-slim
WORKDIR /app
COPY subscriber/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/db.py common/dummy_sensors.py ./
COPY subscriber/validation.py subscriber/subscriber.py subscriber/seed_history.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "subscriber.py"]
