"""图片自动下载打包"""
import hashlib
import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional
import requests

logger = logging.getLogger(__name__)

_STORAGE_DIR = Path(__file__).resolve().parent.parent.parent / "storage" / "image-packs"


def _ensure_dir():
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)


def download_image(url: str, dest: Path, timeout: int = 15, retries: int = 3) -> Optional[str]:
    if not url:
        return None
    # PDD 图片需要 Referer
    referer = "https://mobile.yangkeduo.com/" if "pdd" in url or "yangkeduo" in url else ""
    ua_list = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Mobile/15E148 Safari/604.1",
    ]
    last_error = ""
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": ua_list[attempt % 2],
                "Accept": "image/avif,image/webp,image/apng,*/*",
            }
            if referer:
                headers["Referer"] = referer
            r = requests.get(url, timeout=timeout, headers=headers, stream=True)
            if r.status_code >= 400:
                last_error = f"HTTP {r.status_code}"
                continue
            dest.write_bytes(r.content)
            if len(r.content) < 100:
                last_error = f"Too small ({len(r.content)} bytes)"
                continue
            sha = hashlib.sha256(r.content).hexdigest()
            return sha
        except requests.Timeout:
            last_error = "Timeout"
        except Exception as e:
            last_error = str(e)[:50]
    logger.warning("Download failed after %d retries: %s -> %s", retries, url[:60], last_error)
    return None


def _collect_image_urls(opportunity: dict) -> list:
    """从机会对象中提取所有图片URL"""
    urls = []
    for key in ["sell_image", "buy_image", "image_url", "sell_img", "buy_img"]:
        v = opportunity.get(key, "")
        if v:
            urls.append(v)
    return urls


def generate_image_pack(opportunity: dict, product_family_id: str = "") -> dict:
    """生成图片压缩包，返回 pack_info dict"""
    _ensure_dir()
    title = (opportunity.get("buy_title") or opportunity.get("title", "未知商品"))[:50]
    safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:30]
    folder_name = f"{product_family_id or 'item'}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    folder = _STORAGE_DIR / folder_name
    folder.mkdir(parents=True, exist_ok=True)

    images = _collect_image_urls(opportunity)
    manifest = []
    downloaded = 0
    failed = 0

    for idx, url in enumerate(images):
        ext = os.path.splitext(url.split("?")[0])[1] or ".jpg"
        fname = f"image_{idx:02d}{ext}"
        dest = folder / fname
        sha = download_image(url, dest)
        if sha:
            manifest.append({
                "filename": fname,
                "url": url,
                "sha256": sha,
                "type": "cover" if idx == 0 else f"detail_{idx:02d}"
            })
            downloaded += 1
        else:
            manifest.append({"filename": fname, "url": url, "sha256": "", "type": "failed"})
            failed += 1

    # 写入 manifest.json
    manifest_info = {
        "product_family_id": product_family_id or opportunity.get("id", ""),
        "title": title,
        "source": opportunity.get("buy_platform", "unknown"),
        "image_count": len(images),
        "downloaded": downloaded,
        "failed": failed,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "images": manifest,
    }
    (folder / "manifest.json").write_text(
        json.dumps(manifest_info, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 打包 zip
    zip_path = _STORAGE_DIR / f"{folder_name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for fname in os.listdir(folder):
            zf.write(folder / fname, arcname=f"{folder_name}/{fname}")

    logger.info("Image pack created: %s (%d/%d images)", zip_path, downloaded, len(images))
    return {
        "pack_id": folder_name,
        "title": title,
        "image_count": len(images),
        "downloaded": downloaded,
        "failed": failed,
        "zip_path": str(zip_path),
        "zip_size": os.path.getsize(zip_path),
        "folder": str(folder),
        "manifest": manifest_info,
        "created_at": manifest_info["created_at"],
    }


def get_pack_zip_path(pack_id: str) -> Optional[Path]:
    """获取 zip 文件路径"""
    p = _STORAGE_DIR / f"{pack_id}.zip"
    return p if p.exists() else None


def cleanup_old_packs(hours: int = 72):
    """清理过期压缩包"""
    cutoff = datetime.now().timestamp() - hours * 3600
    for f in _STORAGE_DIR.iterdir():
        if f.is_file() and f.suffix in (".zip",) and f.stat().st_mtime < cutoff:
            f.unlink()
            logger.info("Cleaned up old pack: %s", f.name)
    for d in _STORAGE_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < cutoff:
            shutil.rmtree(d, ignore_errors=True)
            logger.info("Cleaned up old pack folder: %s", d.name)
