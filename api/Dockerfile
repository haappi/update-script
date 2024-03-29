FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app

ENTRYPOINT ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "80", "--proxy-headers"]
