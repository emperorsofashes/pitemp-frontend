FROM python:3.11-slim

# Set the working directory
WORKDIR /app

# Copy the current directory contents into the container at /app
COPY . /app

# Install required Python packages
# Use --no-cache-dir to reduce the size of the layer since we only need to install once
RUN pip install --no-cache-dir -r requirements.txt

# Run the application
CMD ["python3", "-m", "application"]
