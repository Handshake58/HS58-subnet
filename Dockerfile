FROM python:3.11-slim

WORKDIR /app

# System dependencies (git required for runtime auto-update)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# Clone repo so .git is present for auto-update at runtime
ARG REPO_URL=https://github.com/Handshake58/HS58-subnet.git
ARG BRANCH=main
RUN git clone --branch ${BRANCH} --single-branch ${REPO_URL} .

# Install Python dependencies and the subnet58 package
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -e .

RUN chmod +x entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
