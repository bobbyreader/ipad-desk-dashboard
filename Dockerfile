FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends openssh-client && \
    rm -rf /var/lib/apt/lists/*

ARG PIP_INDEX_URL=https://pypi.org/simple
COPY requirements.txt .
RUN pip install --no-cache-dir -i "${PIP_INDEX_URL}" -r requirements.txt

COPY *.py *.html *.css *.js stations.json remote_router.sh config.example.json ./
RUN mkdir -p /app/data

EXPOSE 8788

CMD ["python", "-u", "server.py"]
