# Only used to run a SIMULATED Pi on the laptop:
#   docker compose --profile simulator up -d
# On the real Raspberry Pi you run node.py in a virtual environment instead.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db.py sensors.py node.py ./
ENV PYTHONUNBUFFERED=1
CMD ["python", "node.py"]
