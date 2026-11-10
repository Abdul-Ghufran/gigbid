FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir "fastapi==0.115.12" "uvicorn[standard]==0.34.2" "pydantic==2.11.4" "httpx==0.28.1" "psycopg[binary]==3.2.9"
COPY gigsim ./gigsim
EXPOSE 8081
CMD ["uvicorn", "gigsim.app:app", "--host", "0.0.0.0", "--port", "8081"]
