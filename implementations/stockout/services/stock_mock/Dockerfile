FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

RUN pip install --no-cache-dir \
    "fastapi==0.104.1" \
    "uvicorn[standard]==0.24.0"

COPY examples/__init__.py ./examples/__init__.py
COPY examples/stock_inventory_service/ ./examples/stock_inventory_service/

EXPOSE 8890

CMD ["uvicorn", "examples.stock_inventory_service.http_app:app", "--host", "0.0.0.0", "--port", "8890"]
