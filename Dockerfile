# Dockerfile
FROM python:3.11-slim

# set environment
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

WORKDIR /app

# install system deps
RUN apt-get update && apt-get install -y build-essential libpq-dev pkg-config default-libmysqlclient-dev --no-install-recommends && rm -rf /var/lib/apt/lists/*

# copy requirements first for caching
COPY requirements.txt /app/
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# copy project
COPY . /app/

# collect static (if you use collectstatic)
# RUN python manage.py collectstatic --noinput

EXPOSE 8000

# run migrations and start gunicorn (entrypoint)
CMD ["gunicorn", "project.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2"]
