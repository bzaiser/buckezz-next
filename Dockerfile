FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PYTHONPATH=/opt/ds-pkg
ENV DESIGN_STUDIO_TARGET=/opt/ds-pkg
ENV PIP_CACHE_DIR=/tmp/pip-cache

WORKDIR /app

RUN mkdir -p /opt/ds-pkg && chmod 777 /opt/ds-pkg

RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    libcairo2-dev \
    pkg-config \
    python3-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "--noreload", "0.0.0.0:8000"]
