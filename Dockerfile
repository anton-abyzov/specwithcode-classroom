FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn
COPY swc_classroom swc_classroom
COPY static static
ENV PORT=8080
CMD exec uvicorn swc_classroom.app:app --host 0.0.0.0 --port $PORT
