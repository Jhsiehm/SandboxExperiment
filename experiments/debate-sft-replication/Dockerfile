FROM python:3.12-slim
WORKDIR /app
COPY prepare.py test_prepare.py /app/
COPY inputs /app/inputs
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["python", "/app/prepare.py"]
