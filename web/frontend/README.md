# AgentPipe Frontend

Interactive DAG visualization and pipeline control. Separate service from the backend.

## Run

```bash
bun install
bun start           # http://0.0.0.0:3000
```

## Configure

Edit `.env`:

```
REACT_APP_API_URL=http://localhost:8420
```

## Build

```bash
bun run build       # output in build/
```

## Docker

```bash
docker build -t agentpipe-frontend .
docker run -p 3000:80 agentpipe-frontend
```
