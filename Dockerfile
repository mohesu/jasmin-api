# Use an official Python image as the base
FROM python:3.11-alpine

# Install build tools and system dependencies
RUN apk add --no-cache \
    bash \
    gcc \
    musl-dev \
    linux-headers \
    busybox-extras

# Set the working directory
WORKDIR /app

# Install pipenv or any other dependency manager if needed
# RUN pip install pipenv

# Copy application code to the container
COPY . .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Collect static files
RUN python jasmin_api/manage.py collectstatic --noinput

# Ensure the entrypoint script is executable
RUN chmod +x entrypoint.sh
RUN chmod +x jasmin_api/create_user.py

# Expose the required ports
EXPOSE 8000 8080

# Set environment variables (optional, can also be set via docker-compose)
ENV PYTHONUNBUFFERED=1

# Set entrypoint and default command
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "jasmin_api.wsgi:application", "--bind", "0.0.0.0:8000"]
