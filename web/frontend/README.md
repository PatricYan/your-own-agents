# AgentPipe Frontend

Interactive DAG visualization and pipeline control UI.

The frontend and backend are **two separate services** that communicate only through the API. No proxy. No shared process.

## Quick Start

```bash
# 1. Start the backend (separate terminal)
agentpipe serve --port 8420

# 2. Start the frontend
cd web/frontend
npm install         # first time only
npm start           # opens at http://0.0.0.0:3000
```

## Configure Backend URL

Edit `.env`:

```
REACT_APP_API_URL=http://localhost:8420
```

Or set as environment variable:

```bash
REACT_APP_API_URL=http://192.168.1.100:9000 npm start
```

For production builds, set the URL before building:

```bash
REACT_APP_API_URL=http://api.example.com:8420 npm run build
```

## Production Build

```bash
npm run build
```

The `build/` directory contains static HTML/JS/CSS files.
Serve with any static file server:

```bash
cd build
python -m http.server 3000      # Python
npx serve -s . -l 3000         # Node
# Or nginx, caddy, S3, etc.
```

## Architecture

```
src/
├── api.ts              # API client — connects to REACT_APP_API_URL
├── types.ts            # TypeScript interfaces
├── App.tsx             # Main page — React Flow canvas + WebSocket
└── components/
    ├── TaskNode.tsx     # DAG node (status colors, permissions, model)
    ├── Sidebar.tsx      # Task detail panel (edit goal, permissions, prompt)
    └── Toolbar.tsx      # Run / Pause / Resume controls
```

The frontend connects to the backend via:
- `REACT_APP_API_URL` environment variable (configured in `.env`)
- Default: `http://localhost:8420`
- WebSocket: derived from the API URL (`ws://` instead of `http://`)
