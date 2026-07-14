# --- stage 1: build the React UI -----------------------------------------
FROM node:20-slim AS ui
WORKDIR /ui
COPY webapp/frontend/package.json webapp/frontend/package-lock.json* ./
RUN npm install
COPY webapp/frontend/ .
RUN npm run build   # emits ../static, i.e. /ui/../static -> configured outDir

# --- stage 2: python runtime ----------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Layer-cache dependencies separately from source code.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

COPY pii_redactor/ pii_redactor/
COPY webapp/main.py webapp/__init__.py webapp/
COPY --from=ui /static webapp/static/

# Railway injects PORT; default for local docker runs.
ENV PORT=8000
EXPOSE 8000

CMD uvicorn webapp.main:app --host 0.0.0.0 --port ${PORT}
