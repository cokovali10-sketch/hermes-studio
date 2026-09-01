"""Screenshot diff — pixel-by-pixel comparison returning changed regions."""
from __future__ import annotations

import pathlib


async def diff_screenshots(img1_path: str, img2_path: str) -> dict:
    try:
        from PIL import Image
    except ImportError:
        return {"success": False, "error": "Pillow not installed. Run: pip install Pillow"}

    try:
        p1 = pathlib.Path(img1_path)
        p2 = pathlib.Path(img2_path)

        if not p1.exists():
            return {"success": False, "error": f"File not found: {img1_path}"}
        if not p2.exists():
            return {"success": False, "error": f"File not found: {img2_path}"}

        img1 = Image.open(str(p1)).convert("RGB")
        img2 = Image.open(str(p2)).convert("RGB")

        if img1.size != img2.size:
            return {
                "success": False,
                "error": f"Size mismatch: {img1.size} vs {img2.size}",
            }

        w, h = img1.size
        pixels1 = list(img1.getdata())
        pixels2 = list(img2.getdata())

        diff_pixels = []
        changed_regions = []
        threshold = 30

        for i, (p1, p2) in enumerate(zip(pixels1, pixels2)):
            r_diff = abs(p1[0] - p2[0])
            g_diff = abs(p1[1] - p2[1])
            b_diff = abs(p1[2] - p2[2])
            if r_diff + g_diff + b_diff > threshold:
                x = i % w
                y = i // w
                diff_pixels.append((x, y))
                if len(changed_regions) < 20:
                    changed_regions.append({"x": x, "y": y, "color1": list(p1), "color2": list(p2)})

        total = w * h
        change_ratio = len(diff_pixels) / total if total > 0 else 0

        from PIL import Image as PILImage
        diff_img = PILImage.new("RGB", (w, h), (0, 0, 0))
        for x, y in diff_pixels[:50000]:
            diff_img.putpixel((x, y), (255, 0, 0))

        import io, base64
        buf = io.BytesIO()
        diff_img.save(buf, format="PNG")
        diff_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        return {
            "success": True,
            "identical": len(diff_pixels) == 0,
            "changed_pixels": len(diff_pixels),
            "total_pixels": total,
            "change_ratio": round(change_ratio, 4),
            "changed_regions": changed_regions,
            "diff_image_base64": diff_b64,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
