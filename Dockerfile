FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY api.py mapping.py database.py products.db ./

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "api:app"]
