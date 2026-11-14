FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
# Modelo de vetores do roteador (uns 240 MB), baixado antes do código: o Docker reaproveita esta camada a cada edição.
# Sem acesso ao Hugging Face o build continua e o roteador fica só com o classificador por letras; GET /health mostra router_mode.
COPY src/app/__init__.py src/app/embeddings.py src/app/
RUN python -c "from app import embeddings; print('modelo de vetores:', 'baixado' if embeddings.available() else 'INDISPONIVEL: roteador so por letras')"
# Daqui em diante o modelo só é lido do disco: o container nunca baixa nada nem treina de novo ao subir.
ENV EMBEDDINGS=cached
COPY . .
# Classificador treinado no build: mesma versão do scikit-learn que vai rodar. Cada RUN falha sozinho se der erro.
RUN python scripts/gen_router_data.py
RUN python scripts/train_router.py
EXPOSE 8000
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
