FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY *.py *.html *.css *.js stations.json remote_router.sh config.example.json ./
RUN mkdir -p /app/data

EXPOSE 8788

CMD ["python", "-u", "server.py"]
