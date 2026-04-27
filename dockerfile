# Stage 1: Builder stage
FROM 172.16.83.81:8000/library/python:3.12.12-bookworm AS builder

RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" >/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >>/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free non-free-firmware" >>/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >>/etc/apt/sources.list
    
# Install uv
RUN apt-get update -y 
RUN pip install uv
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    exiftool


# Cleanup
RUN rm -rf /var/lib/apt/lists/*


# Set the working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt /app/

# Create a virtual environment and install dependencies with uv
RUN uv venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
RUN uv pip install --no-cache-dir -r requirements.txt

# Stage 2: Final stage
FROM 172.16.83.81:8000/library/python:3.12.12-bookworm

# Install runtime system dependencies
RUN echo "deb https://mirrors.aliyun.com/debian/ bookworm main contrib non-free non-free-firmware" >/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-updates main contrib non-free non-free-firmware" >>/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian/ bookworm-backports main contrib non-free non-free-firmware" >>/etc/apt/sources.list && \
    echo "deb https://mirrors.aliyun.com/debian-security/ bookworm-security main contrib non-free non-free-firmware" >>/etc/apt/sources.list && \
    apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        exiftool \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set the working directory and ownership preemptively
WORKDIR /app
RUN chown appuser:appuser /app

# Copy the virtual environment from the builder stage
COPY --from=builder /app/venv /app/venv
RUN chown -R appuser:appuser /app/venv

# Set environment path
ENV PATH="/app/venv/bin:$PATH"

# Switch to non-root user before copying application code
USER appuser

# Copy only the application code with correct ownership using --chown
COPY --chown=appuser:appuser . /app/

# Make port available
EXPOSE 8490

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8490"]
