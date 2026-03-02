FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY api.py mapping.py mapping_v2.py database.py protocol_parser.py vision.py qfix_services_by_type.json ./
COPY widget/ ./widget/
COPY docs/ ./docs/
COPY shop/ ./shop/

EXPOSE 8080

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--timeout", "600", "--workers", "1", "--threads", "4", "api:app"]
