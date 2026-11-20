import os
import time
import json
import asyncio
from urllib.parse import urlencode, urlsplit, urlunsplit, parse_qsl

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response, StreamingResponse

UPSTREAM = os.getenv("XT_UPSTREAM", "http://isl-st4k.xyz").rstrip("/")
XT_USER = os.getenv("XT_USER", "c732790d0adb")
XT_PASS = os.getenv("XT_PASS", "053e93ae7d")

app = FastAPI()
client = httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(30.0, read=None))

def inject_creds(url: str) -> str:
    parts = urlsplit(url)
    q = dict(parse_qsl(parts.query, keep_blank_values=True))
    q["username"] = XT_USER
    q["password"] = XT_PASS
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), parts.fragment))

def clean_headers(headers: dict) -> dict:
    drop = {"host", "connection", "content-length", "transfer-encoding", "accept-encoding"}
    return {k: v for k, v in headers.items() if k.lower() not in drop}

@app.api_route("/{path:path}", methods=["GET", "HEAD", "POST"])
async def proxy(path: str, request: Request):
    upstream_url = f"{UPSTREAM}/{path}"
    if request.url.query:
        upstream_url += "?" + request.url.query
    upstream_url = inject_creds(upstream_url)
    
    headers = clean_headers(dict(request.headers))
    if "user-agent" not in {k.lower() for k in headers}:
        headers["user-agent"] = "Mozilla/5.0"

    if path.endswith("player_api.php"):
        r = await client.request(request.method, upstream_url, headers=headers, content=await request.body())
        print(f"--- API REQUEST ---")
        print(f"URL: {upstream_url}")
        print(f"STATUS: {r.status_code}")
        print(f"RESPONSE: {r.text[:100]}") # Print first 100 chars
        
        try:
            data = r.json()
            if "user_info" in data:
                data["user_info"]["exp_date"] = "4102444800"
                data["user_info"]["status"] = "Active"
                data["user_info"]["auth"] = 1
            return Response(content=json.dumps(data).encode(), status_code=200, media_type="application/json")
        except Exception as e:
            print(f"JSON PARSE ERROR: {e}")
            pass 
            
    if path.endswith("get.php") or path.endswith("xmltv.php"):
        r = await client.request(request.method, upstream_url, headers=headers)
        return Response(content=r.content, status_code=r.status_code, headers=clean_headers(dict(r.headers)), media_type=r.headers.get("content-type"))

    if path.startswith("live/") or path.startswith("movie/") or path.startswith("series/"):
        req = client.build_request(request.method, upstream_url, headers=headers)
        r = await client.send(req, stream=True)
        return StreamingResponse(r.aiter_raw(), status_code=r.status_code, headers=clean_headers(dict(r.headers)), media_type=r.headers.get("content-type"))

    r = await client.request(request.method, upstream_url, headers=headers)
    return Response(content=r.content, status_code=r.status_code, headers=clean_headers(dict(r.headers)), media_type=r.headers.get("content-type"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)
