FROM node:20-bookworm-slim AS frontend-build

WORKDIR /frontend

COPY frontend/package.json ./

RUN npm install --include=dev --no-audit --no-fund

COPY frontend/ ./

RUN npm run build

FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./backend
COPY --from=frontend-build /frontend/dist ./frontend_dist
ENV PORT=8000
CMD uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT}
