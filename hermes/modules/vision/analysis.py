"""Image analysis — UI element detection, screenshot comparison, text extraction."""
from __future__ import annotations

import base64
import io


def _decode_b64_image(image_b64: str):
    try:
        from PIL import Image
        img_data = base64.b64decode(image_b64)
        return Image.open(io.BytesIO(img_data))
    except Exception:
        return None


async def analyze_ui_screenshot(image_b64: str) -> dict:
    try:
        img = _decode_b64_image(image_b64)
        if img is None:
            return {"success": False, "error": "Failed to decode image"}

        w, h = img.size
        pixels = list(img.getdata())

        dark_count = sum(1 for p in pixels if (p[0] + p[1] + p[2]) / 3 < 80)
        light_count = sum(1 for p in pixels if (p[0] + p[1] + p[2]) / 3 > 200)
        total = len(pixels)

        regions = []
        if dark_count / total > 0.3:
            regions.append("likely_dark_header_or_sidebar")
        if light_count / total > 0.6:
            regions.append("predominantly_light_content_area")

        return {
            "success": True,
            "width": w,
            "height": h,
            "total_pixels": total,
            "dark_ratio": round(dark_count / total, 3),
            "light_ratio": round(light_count / total, 3),
            "detected_regions": regions,
            "estimated_ui_type": "dark_mode" if dark_count / total > 0.3 else "light_mode",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def compare_screenshots(img1_b64: str, img2_b64: str) -> dict:
    try:
        img1 = _decode_b64_image(img1_b64)
        img2 = _decode_b64_image(img2_b64)
        if img1 is None or img2 is None:
            return {"success": False, "error": "Failed to decode one or both images"}

        if img1.size != img2.size:
            return {
                "success": True,
                "identical": False,
                "reason": "Different dimensions",
                "img1_size": img1.size,
                "img2_size": img2.size,
            }

        from PIL import ImageChops
        diff = ImageChops.difference(img1.convert("RGB"), img2.convert("RGB"))
        bbox = diff.getbbox()

        if bbox is None:
            return {"success": True, "identical": True, "changed_pixels": 0, "total_pixels": img1.size[0] * img1.size[1]}

        changed_pixels = sum(1 for p in diff.getdata() if any(c > 10 for c in p[:3]))

        return {
            "success": True,
            "identical": False,
            "changed_pixels": changed_pixels,
            "total_pixels": img1.size[0] * img1.size[1],
            "change_ratio": round(changed_pixels / (img1.size[0] * img1.size[1]), 4),
            "changed_region": {"x": bbox[0], "y": bbox[1], "w": bbox[2] - bbox[0], "h": bbox[3] - bbox[1]},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


async def extract_text_from_image(image_b64: str) -> dict:
    try:
        img = _decode_b64_image(image_b64)
        if img is None:
            return {"success": False, "error": "Failed to decode image"}

        gray = img.convert("L")
        w, h = gray.size
        pixels = list(gray.getdata())

        threshold = 128
        rows = []
        for y in range(h):
            row_start = y * w
            row = pixels[row_start:row_start + w]
            line = ""
            for px in row:
                line += "#" if px < threshold else " "
            stripped = line.rstrip()
            if stripped:
                rows.append(stripped)

        return {
            "success": True,
            "width": w,
            "height": h,
            "text_rows": len(rows),
            "note": "Basic binary extraction — install pytesseract for real OCR",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
