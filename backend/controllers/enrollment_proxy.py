from fastapi import APIRouter, Request
from fastapi.responses import Response, HTMLResponse
import httpx
import re
import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/enrollment", tags=["enrollment"])

TARGET_URL = "https://zhs.pt.ouchn.cn"
PROXY_BASE = "/enrollment/proxy"

async def fetch_and_modify_content(url: str, base_url: str, method: str = "GET", data: bytes = None, headers: dict = None):
    async with httpx.AsyncClient(follow_redirects=True, timeout=30.0, verify=False) as client:
        try:
            request_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Origin': TARGET_URL,
                'Referer': TARGET_URL,
            }
            
            if headers:
                request_headers.update(headers)
            
            if method == "POST":
                response = await client.post(url, content=data, headers=request_headers)
            else:
                response = await client.get(url, headers=request_headers)
            
            content_type = response.headers.get('content-type', '')
            content = response.content
            
            if 'application/json' in content_type:
                pass
            elif 'text/html' in content_type or 'text/css' in content_type or 'application/javascript' in content_type or 'text/javascript' in content_type:
                text_content = content.decode('utf-8', errors='ignore')
                
                text_content = re.sub(
                    r'(https?:)?//zhs\.pt\.ouchn\.cn',
                    base_url + PROXY_BASE,
                    text_content
                )
                
                text_content = re.sub(
                    r'(["\'])/(api|zxbm|static|prod-api)',
                    r'\1' + base_url + PROXY_BASE + r'/\2',
                    text_content
                )
                
                text_content = re.sub(
                    r'baseURL\s*[:=]\s*["\']/(api|prod-api)',
                    f'baseURL: "{base_url}{PROXY_BASE}/' + r'\1',
                    text_content
                )
                
                text_content = re.sub(
                    r'baseUrl\s*[:=]\s*["\']/(api|prod-api)',
                    f'baseUrl: "{base_url}{PROXY_BASE}/' + r'\1',
                    text_content
                )
                
                content = text_content.encode('utf-8')
            
            response_headers = {
                'Content-Type': response.headers.get('content-type', 'text/html'),
                'Cache-Control': 'no-cache',
            }
            
            if 'access-control-allow-origin' in response.headers:
                response_headers['Access-Control-Allow-Origin'] = '*'
            
            return Response(
                content=content,
                status_code=response.status_code,
                headers=response_headers
            )
        except Exception as e:
            return Response(
                content=f"Proxy Error: {str(e)}",
                status_code=500
            )

@router.get("/proxy/{path:path}")
async def proxy_get(path: str, request: Request):
    target_url = f"{TARGET_URL}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    if '/api/' in path or path.startswith('api/'):
        logger.info(f"API GET request: {path} -> {target_url}")
    
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'connection']:
            headers[key] = value
    
    return await fetch_and_modify_content(target_url, base_url, "GET", None, headers)

@router.post("/proxy/{path:path}")
async def proxy_post(path: str, request: Request):
    target_url = f"{TARGET_URL}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    logger.info(f"POST proxy request: {path} -> {target_url}")
    
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    
    body = await request.body()
    logger.info(f"POST body length: {len(body)}")
    
    headers = {}
    for key, value in request.headers.items():
        if key.lower() not in ['host', 'connection', 'content-length']:
            headers[key] = value
    
    return await fetch_and_modify_content(target_url, base_url, "POST", body, headers)

@router.options("/proxy/{path:path}")
async def proxy_options(path: str, request: Request):
    return Response(
        status_code=200,
        headers={
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
            'Access-Control-Allow-Headers': '*',
            'Access-Control-Max-Age': '86400',
        }
    )

@router.get("/webview", response_class=HTMLResponse)
async def get_enrollment_webview(request: Request):
    base_url = f"{request.url.scheme}://{request.url.netloc}"
    proxy_url = f"{base_url}{PROXY_BASE}/zxbm/#/home?source=12&schoolid=3184"
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <meta http-equiv="Content-Security-Policy" content="upgrade-insecure-requests">
        <title>开放新生报名</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            html, body {{
                width: 100%;
                height: 100%;
                overflow: hidden;
            }}
            #frame-container {{
                width: 100%;
                height: 100%;
                border: none;
            }}
            .loading {{
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                font-family: Arial, sans-serif;
                z-index: 9999;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            }}
            .spinner {{
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }}
            @keyframes spin {{
                0% {{ transform: rotate(0deg); }}
                100% {{ transform: rotate(360deg); }}
            }}
            .error {{
                display: none;
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                text-align: center;
                font-family: Arial, sans-serif;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                max-width: 80%;
            }}
            .error-icon {{
                font-size: 48px;
                margin-bottom: 20px;
            }}
        </style>
    </head>
    <body>
        <div class="loading" id="loading">
            <div class="spinner"></div>
            <p>正在加载报名系统...</p>
            <p style="font-size: 12px; color: #666; margin-top: 10px;">首次加载可能需要较长时间，请耐心等待</p>
        </div>
        <div class="error" id="error">
            <div class="error-icon">⚠️</div>
            <h3>加载失败</h3>
            <p style="margin-top: 10px; color: #666;">无法加载报名系统，请稍后重试</p>
            <button onclick="location.reload()" style="margin-top: 20px; padding: 10px 20px; background: #667eea; color: white; border: none; border-radius: 5px; cursor: pointer;">重新加载</button>
        </div>
        <iframe 
            id="frame-container"
            src="{proxy_url}"
            frameborder="0"
            sandbox="allow-same-origin allow-scripts allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-downloads"
            allow="geolocation; microphone; camera"
            onload="hideLoading()"
            onerror="showError()"
        ></iframe>
        <script>
            let loadTimeout;
            
            function hideLoading() {{
                clearTimeout(loadTimeout);
                document.getElementById('loading').style.display = 'none';
            }}
            
            function showError() {{
                clearTimeout(loadTimeout);
                document.getElementById('loading').style.display = 'none';
                document.getElementById('error').style.display = 'block';
            }}
            
            // 设置30秒超时
            loadTimeout = setTimeout(function() {{
                const loading = document.getElementById('loading');
                if (loading.style.display !== 'none') {{
                    showError();
                }}
            }}, 30000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
