from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
import os

router = APIRouter(tags=["verification"])

@router.get("/WbSZiSRQCO.txt", response_class=PlainTextResponse)
async def get_verification_file():
    file_path = os.path.join("static", "WbSZiSRQCO.txt")
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return PlainTextResponse(content=content)
    except FileNotFoundError:
        return PlainTextResponse(content="File not found", status_code=404)
