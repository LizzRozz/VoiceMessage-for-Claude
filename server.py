import hashlib, os, uuid, logging
from pathlib import Path
from urllib.parse import urlparse

import mcp.server.transport_security as ts
def _patched_init(self, settings=None):
    self.settings = ts.TransportSecuritySettings(enable_dns_rebinding_protection=False)
ts.TransportSecurityMiddleware.__init__ = _patched_init

import httpx
import uvicorn
from starlette.middleware.cors import CORSMiddleware
from starlette.routing import Route
from starlette.responses import FileResponse, JSONResponse
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voicemsg")

AUDIO_DIR = Path(os.environ.get("AUDIO_DIR", "./audio_cache"))
PORT = int(os.environ.get("PORT", "8001"))
BASE_URL = os.environ.get("BASE_URL", "")
MCP_SERVER_URL = os.environ.get("MCP_SERVER_URL", "")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

RESOURCE_URI = "ui://voice-player"


#===================================================
#TTS Interface / 语音合成接口
#Plug in your voice API here / 在这里接入你的语音 API
#===================================================

async def synthesize(text: str, filepath: Path) -> None:
    """
    Synthesize text to speech and write MP3 audio to filepath.
    将文本合成为语音，写入 filepath。

    text:     The text to synthesize / 要合成的文本
    filepath: Output path, must write MP3 format audio data / 输出文件路径，需写入 MP3 格式的音频数据

    Example (pseudocode) / 示例（伪代码）:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://your-tts-api.com/v1/tts",
                json={"text": text, "voice": "your-voice-id"},
                headers={"Authorization": "Bearer " + os.environ["YOUR_API_KEY"]},
            )
            response.raise_for_status()
            filepath.write_bytes(response.content)
    """
    raise NotImplementedError("Please implement your TTS API here - see comments above")

# ─────────────────────────────────────────────


def _origin(url: str) -> str | None:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return None
    return f"{parsed.scheme}://{parsed.netloc}"

def _resource_domains() -> list[str]:
    base = BASE_URL.rstrip("/") if BASE_URL else f"http://localhost:{PORT}"
    origin = _origin(base)
    return [origin] if origin else []

def _claude_app_domain() -> str | None:
    server_url = MCP_SERVER_URL.rstrip("/")
    if not server_url:
        base = BASE_URL.rstrip("/")
        server_url = f"{base}/mcp" if base else f"http://localhost:{PORT}/mcp"
    if not server_url.startswith("https://"):
        return None
    digest = hashlib.sha256(server_url.encode("utf-8")).hexdigest()[:32]
    return f"{digest}.claudemcpcontent.com"

def _ui_meta() -> dict:
    ui = {
        "csp": {
            "resourceDomains": _resource_domains(),
        },
        "prefersBorder": False,
    }
    domain = _claude_app_domain()
    if domain:
        ui["domain"] = domain
    return {"ui": ui}

UI_META = _ui_meta()

PLAYER_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;background:transparent;display:flex;align-items:center;justify-content:flex-start;min-height:56px;padding:8px 8px 8px 16px}
.player{display:inline-flex;align-items:center;justify-content:space-between;gap:14px;width:184px;padding:12px 17px;border:1px solid #94938b;border-radius:9px;background:#2b2b29;box-shadow:0 8px 18px rgba(23,23,23,0.08);cursor:pointer;transition:background 0.15s,transform 0.12s,width 0.2s}
.player:hover{background:#2b2b29}
.player:active{transform:scale(0.985)}
.player.playing{background:#2b2b29}
.icon{width:21px;height:21px;flex:0 0 21px;fill:#eeeeea;margin-left:-3px}
.pause-icon{display:none}
.player.playing .play-icon{display:none}
.player.playing .pause-icon{display:block}
.duration{color:#eeeeea;font-size:15px;line-height:1;font-variant-numeric:tabular-nums;white-space:nowrap}
.loading{color:#8b8b86;font-size:12px;text-align:center;width:100%}
</style></head><body>
<div class="loading" id="loading">loading...</div>
<div class="player" id="player" style="display:none" role="button" tabindex="0" aria-label="Play voice message">
  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
    <polygon class="play-icon" points="6,4 21,12 6,20"/>
    <g class="pause-icon">
      <rect x="7" y="5" width="4" height="14" rx="1"/>
      <rect x="14" y="5" width="4" height="14" rx="1"/>
    </g>
  </svg>
  <span class="duration" id="dur">0''</span>
</div>
<script>
let audio=null,playing=false;
const playerEl=document.getElementById('player'),loadingEl=document.getElementById('loading'),durEl=document.getElementById('dur');
function fmtSeconds(s){const sec=Math.max(1,Math.round(Number(s)||0));return sec+"''"}
function widthForSeconds(s){const sec=Math.max(1,Math.round(Number(s)||0));return Math.min(300,Math.max(148,136+sec*2.6))}
function applyDuration(s){const sec=Math.max(1,Math.round(Number(s)||0));durEl.textContent=fmtSeconds(sec);playerEl.style.width=widthForSeconds(sec)+'px'}
function togglePlayback(){if(!audio)return;if(playing){audio.pause();setPaused();return}audio.play().then(setPlaying).catch(()=>setPaused())}
playerEl.addEventListener('click',togglePlayback);
playerEl.addEventListener('keydown',(e)=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();togglePlayback()}});
function setPlaying(){playing=true;playerEl.classList.add('playing');playerEl.setAttribute('aria-label','Pause voice message')}
function setPaused(){playing=false;playerEl.classList.remove('playing');playerEl.setAttribute('aria-label','Play voice message')}
function notifySize(){sendNotification('ui/notifications/size-changed',{width:document.body.scrollWidth,height:document.body.scrollHeight})}
function loadAudio(data){const url=typeof data==='string'?data:data.audio_url;const hintedDuration=typeof data==='object'?data.duration:null;if(audio){audio.pause();audio.src=''}setPaused();audio=document.createElement('audio');audio.crossOrigin='anonymous';audio.preload='auto';audio.src=url;if(hintedDuration)applyDuration(hintedDuration);audio.addEventListener('loadedmetadata',()=>{applyDuration(audio.duration||hintedDuration);loadingEl.style.display='none';playerEl.style.display='inline-flex';setTimeout(notifySize,0)});audio.addEventListener('canplay',()=>{loadingEl.style.display='none';playerEl.style.display='inline-flex';setTimeout(notifySize,0)});audio.addEventListener('ended',()=>{setPaused();audio.currentTime=0});audio.addEventListener('error',()=>{loadingEl.textContent='failed to load';loadingEl.style.display='block';playerEl.style.display='none';setTimeout(notifySize,0)});audio.load()}
function firstToolData(value){
  if(!value||typeof value!=='object')return null;
  if(typeof value.audio_url==='string')return {audio_url:value.audio_url,duration:value.duration};
  const candidates=[
    value.structuredContent,
    value.toolOutput,
    value.result,
    value.result&&value.result.structuredContent,
    value.params,
    value.params&&value.params.structuredContent,
    value.params&&value.params.result,
    value.params&&value.params.result&&value.params.result.structuredContent
  ];
  for(const candidate of candidates){
    const data=firstToolData(candidate);
    if(data)return data;
  }
  return null;
}
function consumeToolData(value){
  const data=firstToolData(value);
  if(data)loadAudio(data);
}
function sendNotification(method,params){
  window.parent.postMessage({jsonrpc:'2.0',method,params:params||{}},'*');
}
function initializeMcpApp(){
  const id='voice-player-init-'+Date.now();
  const onMessage=(e)=>{
    if(e.data&&e.data.jsonrpc==='2.0'&&e.data.id===id){
      window.removeEventListener('message',onMessage);
      sendNotification('ui/notifications/initialized',{});
      notifySize();
    }
  };
  window.addEventListener('message',onMessage);
  window.parent.postMessage({
    jsonrpc:'2.0',
    id,
    method:'ui/initialize',
    params:{
      protocolVersion:'2026-01-26',
      appInfo:{name:'Voice Player',version:'1.0.0'},
      appCapabilities:{availableDisplayModes:['inline']}
    }
  },'*');
}
window.addEventListener('message',(e)=>{
  if(!e.data)return;
  consumeToolData(e.data);
  if(e.data.jsonrpc==='2.0'&&(e.data.method==='ui/notifications/tool-result'||e.data.method==='ui/toolResult')){
    consumeToolData(e.data.params);
  }
});
window.addEventListener('openai:set_globals',()=>consumeToolData(window.openai));
if(window.openai)consumeToolData(window.openai);
initializeMcpApp();
</script></body></html>"""

mcp = FastMCP("VoiceMessage")

@mcp.resource(RESOURCE_URI, name="Voice Player", mime_type="text/html;profile=mcp-app")
def voice_player_resource():
    return PLAYER_HTML

@mcp.tool(meta={"ui": {"resourceUri": RESOURCE_URI}})
async def speak(text: str) -> CallToolResult:
    """Convert text to a voice message.
    Args:
        text: The text to speak
    """
    if not text.strip():
        return CallToolResult(content=[TextContent(type="text", text="Please provide some text")])
    try:
        file_id = uuid.uuid4().hex[:12]
        filename = f"{file_id}.mp3"
        filepath = AUDIO_DIR / filename

        await synthesize(text.strip(), filepath)

        file_size = filepath.stat().st_size
        duration = max(1, int(file_size / 16000))
        base = BASE_URL.rstrip("/") if BASE_URL else f"http://localhost:{PORT}"
        audio_url = f"{base}/audio/{filename}"
        logger.info(f"Generated: {filename} | {file_size}B | ~{duration}s")
        return CallToolResult(
            content=[TextContent(type="text", text=f"Generated (~{duration}s)\n{audio_url}")],
            structuredContent={"audio_url": audio_url, "duration": duration, "text": text},
            _meta={"ui": {"resourceUri": RESOURCE_URI}},
        )
    except NotImplementedError as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error: {e}")])
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return CallToolResult(content=[TextContent(type="text", text=f"TTS failed: {str(e)}")])


# Patch tool meta at runtime / 运行时注入 tool 元数据
try:
    mcp._tool_manager._tools['speak'].meta = {"ui": {"resourceUri": RESOURCE_URI}}
    logger.info("Patched speak tool meta successfully")
except Exception as e:
    logger.warning(f"Failed to patch tool meta: {e}")


# FastMCP 1.x does not expose UI resource metadata through the decorator.
# Claude uses this metadata to construct the iframe CSP.
# FastMCP 1.x 不通过装饰器暴露 UI 资源元数据，需要手动注入 CSP 信息。
_read_resource = mcp.read_resource

async def _read_resource_with_ui_meta(uri):
    contents = await _read_resource(uri)
    if str(uri) == RESOURCE_URI:
        for content in contents:
            if hasattr(content, "meta"):
                content.meta = UI_META
    return contents

try:
    mcp._mcp_server.read_resource()(_read_resource_with_ui_meta)
    logger.info("Patched UI resource meta successfully")
except Exception as e:
    logger.warning(f"Failed to patch UI resource meta: {e}")


async def serve_audio(request):
    filename = request.path_params["filename"]
    if "/" in filename or ".." in filename:
        return JSONResponse({"error": "invalid"}, status_code=400)
    filepath = AUDIO_DIR / filename
    if not filepath.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(filepath, media_type="audio/mpeg",
                        headers={"Access-Control-Allow-Origin": "*"})


if __name__ == "__main__":
    logger.info(f"VoiceMessage starting | port={PORT}")
    _app = mcp.streamable_http_app()
    _app.routes.insert(0, Route("/audio/{filename}", serve_audio))
    _app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["*"],
    )
    uvicorn.run(_app, host="0.0.0.0", port=PORT)
