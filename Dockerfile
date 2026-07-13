FROM python:3.12-slim

WORKDIR /app

# Layer-cache dependencies separately from source code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

COPY pii_redactor/ pii_redactor/
COPY webapp/ webapp/

# Railway injects PORT; default for local docker runs.
ENV PORT=8000
EXPOSE 8000

CMD uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT}
