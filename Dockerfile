FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Classificador treinado no build: mesma versão do scikit-learn que vai rodar. Cada RUN falha sozinho se der erro.
RUN python scripts/gen_router_data.py
RUN python scripts/train_router.py
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
