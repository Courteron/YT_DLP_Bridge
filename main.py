# file: yt_downloader_server.py
import asyncio
import websockets
import json
import yt_dlp
import os
import time
from datetime import datetime
from typing import Dict, Any

HOST = "localhost"
PORT = 8765

BASE_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube")
os.makedirs(BASE_DOWNLOAD_DIR, exist_ok=True)

connected: "set[websockets.WebSocketServerProtocol]" = set()
downloads: Dict[str, Dict[str, Any]] = {}
MAIN_LOOP = None

async def broadcast(message: str):
    stale = []
    for ws in list(connected):
        try:
            await ws.send(message)
        except Exception:
            stale.append(ws)
    for ws in stale:
        connected.discard(ws)

def _safe_broadcast_from_thread(payload: dict):
    if MAIN_LOOP is None:
        return
    asyncio.run_coroutine_threadsafe(broadcast(json.dumps(payload)), MAIN_LOOP)

def get_download_subfolder():
    """Return folder path based on current date and hour, e.g., 2025-11-02_14"""
    now = datetime.now()
    folder_name = now.strftime("%Y-%m-%d_%H")
    folder_path = os.path.join(BASE_DOWNLOAD_DIR, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    return folder_path

def run_yt_dlp_download(url: str, video_id: str):
    key = video_id
    start_time = time.time()
    downloads.setdefault(key, {})
    downloads[key].update({
        "videoId": video_id,
        "status": "starting",
        "percent": 0.0,
        "downloaded_bytes": 0,
        "total_bytes": None,
        "speed": None,
        "eta": None,
        "filename": None,
        "title": None,
        "started_at": start_time,
        "finished_at": None,
        "error": None,
    })

    _safe_broadcast_from_thread({
        "event": "download_started",
        "videoId": video_id,
        "status": "starting",
        "timestamp": int(start_time),
    })

    def progress_hook(d):
        try:
            status = d.get("status")
            if status == "downloading":
                downloaded = d.get("downloaded_bytes") or 0
                total = d.get("total_bytes") or None
                percent = round(float(downloaded)/float(total)*100,2) if total else None
                downloads[key].update({
                    "status": "downloading",
                    "percent": percent,
                    "downloaded_bytes": downloaded,
                    "total_bytes": total,
                    "speed": d.get("speed"),
                    "eta": d.get("eta"),
                    "filename": d.get("tmpfilename") or downloads[key].get("filename"),
                })
                _safe_broadcast_from_thread({
                    "event": "progress",
                    "videoId": video_id,
                    "status": "downloading",
                    "percent": downloads[key]["percent"],
                    "downloaded_bytes": downloads[key]["downloaded_bytes"],
                    "total_bytes": downloads[key]["total_bytes"],
                    "speed": downloads[key]["speed"],
                    "eta": downloads[key]["eta"],
                    "filename": downloads[key]["filename"],
                    "timestamp": int(time.time()),
                })
            elif status == "finished":
                filename = d.get("filename")
                downloads[key].update({
                    "status": "extracting",
                    "filename": filename,
                    "percent": 100.0,
                })
                _safe_broadcast_from_thread({
                    "event": "progress",
                    "videoId": video_id,
                    "status": "extracting",
                    "filename": filename,
                    "timestamp": int(time.time()),
                })
        except Exception as e:
            downloads[key].update({"error": str(e)})
            _safe_broadcast_from_thread({
                "event": "error",
                "videoId": video_id,
                "message": f"progress_hook error: {e}"
            })

    download_folder = get_download_subfolder()
    ydl_opts = {
        "outtmpl": os.path.join(download_folder, "%(title)s.%(ext)s"),
        "format": "best[height<=360]+bestaudio/best[height<=360]",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "progress_hooks": [progress_hook],
        "quiet": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title") if isinstance(info, dict) else None
            filename = ydl.prepare_filename(info) if isinstance(info, dict) else None
            downloads[key].update({
                "status": "finished",
                "percent": 100.0,
                "downloaded_bytes": downloads[key].get("total_bytes") or downloads[key].get("downloaded_bytes"),
                "filename": filename,
                "title": title,
                "finished_at": time.time(),
            })
            _safe_broadcast_from_thread({
                "event": "download_complete",
                "videoId": video_id,
                "title": title,
                "filename": filename,
                "timestamp": int(time.time()),
            })
    except Exception as e:
        downloads[key].update({
            "status": "error",
            "error": str(e),
            "finished_at": time.time(),
        })
        _safe_broadcast_from_thread({
            "event": "error",
            "videoId": video_id,
            "message": str(e),
            "timestamp": int(time.time()),
        })

async def handle_client(websocket):
    connected.add(websocket)
    try:
        await websocket.send(json.dumps({"event": "downloads_list", "downloads": downloads}))
        async for message in websocket:
            video_id = None
            try:
                payload = json.loads(message)
                if isinstance(payload, dict) and payload.get("type") == "download":
                    video_id = payload.get("videoId")
                elif isinstance(payload, dict) and "videoId" in payload:
                    video_id = payload.get("videoId")
                else:
                    await websocket.send(json.dumps({"event": "error", "message": "Unknown JSON payload"}))
                    continue
            except json.JSONDecodeError:
                video_id = message.strip()

            if not video_id:
                await websocket.send(json.dumps({"event": "error", "message": "No videoId provided"}))
                continue

            url = f"https://www.youtube.com/watch?v={video_id}"
            if downloads.get(video_id, {}).get("status") in ("downloading", "starting"):
                await websocket.send(json.dumps({"event": "info", "message": "Already downloading", "videoId": video_id}))
                continue

            downloads.setdefault(video_id, {})
            downloads[video_id].update({
                "videoId": video_id,
                "status": "queued",
                "percent": 0.0,
                "queued_at": time.time(),
            })
            await broadcast(json.dumps({"event": "downloads_list", "downloads": downloads}))
            asyncio.get_running_loop().create_task(asyncio.to_thread(run_yt_dlp_download, url, video_id))
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected.discard(websocket)

async def main():
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()
    server = await websockets.serve(handle_client, HOST, PORT)
    print(f"YT-DLP WebSocket server running on ws://{HOST}:{PORT}")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
