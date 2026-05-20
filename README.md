<p align="right">
  <b>English</b> | <a href="./README_CN.md">中文</a>
</p>

<h1 align="center">VoiceMessage-for-Claude</h1>
<p align="center">Give Claude a voice using a custom MCP connector</p>

<!-- <p align="center">
  <img src="./assets/demo.png" width="400" />
</p> -->

An MCP server that turns text into voice messages and plays them through a compact audio player embedded right inside the Claude chat. You bring your own voice API — this project handles the rest: MCP tool definition, audio hosting, player rendering, and Claude iframe handshake.

## How It Works

1. Claude calls the `speak` tool with some text
2. The server sends the text to your configured voice API, generates an MP3, and saves it
3. Claude renders an inline audio player widget — click to play

The player is a self-contained MCP App: pure inline SVG + CSS, no external dependencies.

## Quick Start

### Prerequisites

- A Claude subscription may be required? (MCP connectors seem to require a subscription, but I have an unsubscribed account that also works)
- A VPS or machine with Docker installed
- [Cloudflare Tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) (free) or any other way to expose the server over HTTPS
- A voice API (any service that converts text to MP3)

### 1. Clone and configure

```bash
git clone https://github.com/LizzRozz/VoiceMessage-for-Claude.git
cd VoiceMessage-for-Claude
```

Create a `.env` file:

```env
BASE_URL=https://your-tunnel-domain.trycloudflare.com
```

### 2. Plug in your voice API

Open `server.py` and find the `synthesize` function — this is the only part you need to modify.

See [Voice API Integration](#voice-api-integration) below.

### 3. Start the server

```bash
docker-compose up -d --build
```

### 4. Expose over HTTPS

```bash
cloudflared tunnel --url http://localhost:18002
```

Copy the generated URL, update `BASE_URL` in `.env`, then restart:

```bash
docker-compose up -d
```

### 5. Connect to Claude

In Claude.ai:

1. Go to **Settings → Integrations**
2. Add a new MCP connector
3. Enter: `https://your-tunnel-domain.trycloudflare.com/mcp`

Then ask Claude tp use the tool to say something.

## Voice API Integration

A `synthesize` function is provided in `server.py`:

```python
async def synthesize(text: str, filepath: Path) -> None:
    """
    Convert text to speech and write to filepath.

    text:     the text to synthesize
    filepath: output path for the MP3 file

    Call your voice API here and write the audio data to filepath.
    """
    raise NotImplementedError("Plug in your voice API here")
```

What you need to do:

1. Call your chosen voice platform's API
2. Write the returned MP3 audio data to `filepath`
3. Add any environment variables you need (API key, etc.) to `.env`

The framework handles the rest — file naming, URL generation, player rendering.

## Architecture

```
Claude.ai
  ↓ MCP over HTTPS
Cloudflare Tunnel (free)
  ↓
Your VPS :18002
  ↓
Docker container :8001
  ├── POST /mcp          → MCP endpoint (speak tool)
  ├── GET  /audio/*.mp3  → generated audio files
  └── ui://voice-player  → inline audio player (MCP App)
```

## Project Structure

```
VoiceMessage-for-Claude/
├── server.py              # MCP server, voice synthesis interface, audio route, player widget
├── docker-compose.yml     # container config
├── Dockerfile             # Python 3.12 slim image
├── requirements.txt       # mcp, httpx, uvicorn, starlette
├── .env                   # secrets and config
└── audio_cache/           # generated MP3 files (Docker volume)
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `BASE_URL` | Yes | — | Public HTTPS URL of your server |
| `PORT` | No | `8001` | Internal server port |
| `AUDIO_DIR` | No | `/app/audio_cache` | Where MP3s are stored |

Voice API variables (API key, voice ID, etc.) are up to you — add them to `.env` and `docker-compose.yml` as needed.

## Customization

### Player Appearance

The player HTML/CSS lives in the `PLAYER_HTML` variable in `server.py`. The current color scheme is sampled from the iPhone Claude App dark mode to match Claude's native interface. For iPhone light mode, you can swap the player background to `#FFFFFF` and the border to `#7A7873`. Adjust to taste based on your device or personal preference.

### Connector Icon

The connector icon shown in Claude depends on your domain. If you use a free Cloudflare Tunnel domain, it will show the Cloudflare icon. If you use your own domain (e.g. if you've set up an external memory server), you can customize the connector icon.

## Troubleshooting

**Claude shows "Failed to load the MCP app"**
- Make sure `BASE_URL` is HTTPS, not HTTP
- After code changes, rebuild with `docker-compose up -d --build`

**Audio won't play**
- Check that audio is accessible: `curl -I https://your-domain/audio/somefile.mp3`
- Verify `BASE_URL` matches your actual tunnel URL

**Cloudflare Tunnel URL changed**
- Free tunnels get a new URL on restart
- Update `BASE_URL` in `.env` and restart the container
- Update the connector URL in Claude.ai settings
- For a permanent URL, get your own domain

**Code changes not taking effect**
- After modifying `server.py` / `requirements.txt` / `Dockerfile`, restart with `--build`:

```bash
docker stop voicemsg && docker rm voicemsg
docker-compose up -d --build
```

## Technical Details

The main work in this project is getting the MCP App player to render correctly inside the Claude chat. Key points to note:

**Transport Security Patch**
The MCP SDK enables DNS rebinding protection by default, which blocks requests when running behind a tunnel. `server.py` patches this out at import time.

**Tool Meta Injection**
Claude requires `meta.ui.resourceUri` in the tool definition to trigger MCP App rendering. FastMCP's `@mcp.tool()` decorator supports the `meta` parameter, but some versions require an additional runtime patch on `_tool_manager` to ensure the metadata takes effect.

**UI Resource Meta**
Claude needs CSP and domain information when constructing the iframe. `server.py` patches the `read_resource` method to inject metadata containing `resourceDomains` and a computed `domain` (the first 32 characters of the SHA-256 hash of the MCP server URL). Without this, Claude will show "Failed to load the MCP app".

**MCP Apps Handshake Protocol**
The player iframe must initiate a `ui/initialize` handshake with Claude, wait for confirmation, then send `ui/notifications/initialized`. Tool call results are pushed to the iframe via `ui/notifications/tool-result`. This is barely documented in the official MCP docs.

**structuredContent Delivery**
The `structuredContent` returned by the tool (containing `audio_url` and `duration`) is passed to the iframe via postMessage. The player's JavaScript recursively searches multiple possible data paths for compatibility across different message formats.

## License

MIT
