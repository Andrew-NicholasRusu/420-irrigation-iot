# Build context is ./local (see docker-compose.yml) so common/db.py can be copied in.
FROM python:3.12-slim
WORKDIR /app
COPY web/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY common/db.py ./
COPY web/app.py ./
COPY web/templates ./templates
COPY web/static ./static
ENV PYTHONUNBUFFERED=1
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
