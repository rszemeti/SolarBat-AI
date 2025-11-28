ARG BUILD_FROM
FROM $BUILD_FROM

# Set shell
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# Install system dependencies
RUN apk add --no-cache \
    python3 \
    py3-pip \
    py3-numpy \
    py3-scipy \
    gcc \
    g++ \
    musl-dev \
    python3-dev \
    openblas-dev \
    lapack-dev \
    gfortran

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY run.sh .

# Make run script executable
RUN chmod a+x run.sh

# Run
CMD ["./run.sh"]
