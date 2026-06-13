FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY inditex_audit_server.py .
COPY inditex_audit_dashboard.html .

# EB Docker platform proxies port 80 → 8080 by default.
# Override with PORT env var for local dev (docker-compose uses 5252).
ENV PORT=8080
EXPOSE 8080

CMD ["python", "inditex_audit_server.py"]
