# AgentPipe Backend
#
# Configuration via environment variables (see .env.example).
# No values are hardcoded — pass them via --env-file or docker-compose.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir ".[web]"

COPY examples/ examples/

RUN mkdir -p /app/workspace

# No ENV defaults here. All config comes from:
# 1. --env-file .env (docker run)
# 2. env_file in docker-compose.yml
# 3. Defaults in agentpipe/config.py if nothing is set

CMD ["agentpipe", "serve"]
