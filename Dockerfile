# Dockerfile
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the Flask app code
COPY app.py ./ 
COPY templates ./templates
COPY static ./static

# Expose the Flask default port
EXPOSE 5000

# Define environment variables for Flask
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Run the Flask app on container start
CMD ["python", "-m", "flask", "run", "--host=0.0.0.0"]
