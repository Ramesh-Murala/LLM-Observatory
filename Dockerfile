FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY constraints.txt ./
COPY observatory ./observatory
RUN pip install --no-cache-dir -c constraints.txt '.[postgres]' && useradd --create-home observatory
USER observatory
EXPOSE 8000
CMD ["uvicorn", "observatory.api:app", "--host", "0.0.0.0", "--port", "8000"]
