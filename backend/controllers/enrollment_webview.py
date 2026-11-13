from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response
import httpx
import re

router = APIRouter(prefix="/enrollment", tags=["enrollment"])

TARGET_URL = "https://zhs.pt.ouchn.cn"
TARGET_PATH = "/zxbm/#/home?source=12&schoolid=3184"

@router.get("/webview", response_class=HTMLResponse)
async def get_enrollment_webview():
    html_content = """
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>开放新生报名</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 20px;
            }
            .container {
                background: white;
                border-radius: 20px;
                padding: 40px 30px;
                max-width: 500px;
                width: 100%;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            .logo {
                text-align: center;
                margin-bottom: 30px;
            }
            .logo-circle {
                width: 80px;
                height: 80px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0 auto 15px;
                font-size: 40px;
            }
            h1 {
                color: #333;
                font-size: 24px;
                text-align: center;
                margin-bottom: 10px;
            }
            .subtitle {
                color: #666;
                text-align: center;
                margin-bottom: 30px;
                font-size: 14px;
            }
            .url-box {
                background: #f5f7fa;
                border: 2px dashed #ddd;
                border-radius: 10px;
                padding: 15px;
                margin-bottom: 20px;
                word-break: break-all;
                font-size: 13px;
                color: #555;
                text-align: center;
            }
            .btn {
                width: 100%;
                padding: 15px;
                border: none;
                border-radius: 10px;
                font-size: 16px;
                font-weight: bold;
                cursor: pointer;
                margin-bottom: 15px;
                transition: all 0.3s;
            }
            .btn-primary {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            .btn-primary:active {
                transform: scale(0.98);
            }
            .btn-secondary {
                background: white;
                color: #667eea;
                border: 2px solid #667eea;
            }
            .btn-secondary:active {
                transform: scale(0.98);
            }
            .tips {
                background: #fff3cd;
                border-left: 4px solid #ffc107;
                padding: 12px;
                margin-top: 20px;
                border-radius: 5px;
                font-size: 13px;
                color: #856404;
            }
            .qrcode {
                text-align: center;
                margin-top: 20px;
                padding-top: 20px;
                border-top: 1px solid #eee;
            }
            .qrcode img {
                width: 200px;
                height: 200px;
                margin: 10px auto;
                display: block;
            }
            .qrcode-tip {
                color: #666;
                font-size: 13px;
            }
            .success-msg {
                background: #d4edda;
                color: #155724;
                padding: 10px;
                border-radius: 5px;
                margin-bottom: 15px;
                text-align: center;
                display: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="logo">
                <div class="logo-circle">🎓</div>
            </div>
            <h1>开放新生报名</h1>
            <p class="subtitle">黔东南开放大学在线报名系统</p>
            
            <div class="success-msg" id="successMsg">链接已复制到剪贴板！</div>
            
            <div class="url-box" id="urlBox">
                https://zhs.pt.ouchn.cn/zxbm/#/home?source=12&schoolid=3184
            </div>
            
            <button class="btn btn-primary" onclick="copyUrl()">📋 复制链接</button>
            <button class="btn btn-secondary" onclick="openInBrowser()">🌐 在浏览器中打开</button>
            
            <div class="tips">
                <strong>💡 温馨提示：</strong><br>
                1. 点击"复制链接"后，在浏览器中粘贴访问<br>
                2. 或点击"在浏览器中打开"直接跳转<br>
                3. 建议使用微信、Safari或Chrome浏览器访问
            </div>
            
            <div class="qrcode">
                <div class="qrcode-tip">或扫描下方二维码访问</div>
                <img src="https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=https://zhs.pt.ouchn.cn/zxbm/%23/home?source=12%26schoolid=3184" alt="报名二维码">
            </div>
        </div>
        
        <script>
            const enrollUrl = 'https://zhs.pt.ouchn.cn/zxbm/#/home?source=12&schoolid=3184';
            
            function copyUrl() {
                const urlBox = document.getElementById('urlBox');
                const successMsg = document.getElementById('successMsg');
                
                if (navigator.clipboard && navigator.clipboard.writeText) {
                    navigator.clipboard.writeText(enrollUrl).then(() => {
                        showSuccess();
                    }).catch(() => {
                        fallbackCopy();
                    });
                } else {
                    fallbackCopy();
                }
            }
            
            function fallbackCopy() {
                const textarea = document.createElement('textarea');
                textarea.value = enrollUrl;
                textarea.style.position = 'fixed';
                textarea.style.opacity = '0';
                document.body.appendChild(textarea);
                textarea.select();
                try {
                    document.execCommand('copy');
                    showSuccess();
                } catch (err) {
                    alert('复制失败，请手动复制链接');
                }
                document.body.removeChild(textarea);
            }
            
            function showSuccess() {
                const successMsg = document.getElementById('successMsg');
                successMsg.style.display = 'block';
                setTimeout(() => {
                    successMsg.style.display = 'none';
                }, 3000);
            }
            
            function openInBrowser() {
                window.location.href = enrollUrl;
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)
