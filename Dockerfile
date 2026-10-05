FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/index.html ./
COPY frontend/src ./src
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PORT=10000
COPY backend ./backend
COPY clinic.json ./clinic.json
COPY conversations ./conversations
COPY run.py ./run.py
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
EXPOSE 10000
CMD ["python", "run.py"]
