"""登录相关 API 路由."""
from fastapi import APIRouter, HTTPException
from ..services.qr_login import qr_service

router = APIRouter(prefix="/api/login", tags=["login"])


@router.get("/status")
async def login_status():
    """获取当前登录状态."""
    return qr_service.get_status()


@router.post("/qrcode")
async def get_qrcode():
    """获取登录二维码."""
    try:
        result = await qr_service.get_qrcode()
        if result.get("qrcode"):
            return result
        raise HTTPException(500, "获取二维码失败")
    except Exception as e:
        raise HTTPException(500, f"获取二维码失败: {e}")


@router.get("/check")
async def check_scan():
    """检查扫码状态."""
    return await qr_service.check_scan()


@router.post("/confirm")
async def confirm():
    """确认登录并保存 Cookie."""
    return await qr_service.confirm_login()


@router.post("/logout")
async def logout():
    """清除登录状态."""
    import yaml
    path = qr_service.cookies_path
    if path.exists():
        path.write_text(yaml.dump({
            "msToken": "", "ttwid": "", "odin_tt": "",
            "passport_csrf_token": "", "sid_guard": "",
        }, allow_unicode=True), "utf-8")
    await qr_service.close()
    return {"status": "ok"}
