"""Media processing tools for Hermes agent."""
import asyncio
import json
import pathlib
# --- константы вынесены FORGE refactor ---
CONST_75 = 75
CONST_128 = 128
CONST_255 = 255
CONST_300 = 300
CONST_320 = 320
CONST_600 = 600
CONST_2000 = 2000


TOOLS = [
    {"name": "convert_image", "description": "Convert image from one format to another", "parameters": {"type": "object", "properties": {"input_path": {"type": "string", "description": "Source image path"}, "output_path": {"type": "string", "description": "Destination path"}, "format": {"type": "string", "enum": ["PNG", "JPEG", "WEBP", "BMP", "TIFF", "GIF"], "description": "Target format"}}, "required": ["input_path", "output_path", "format"]}},
    {"name": "resize_image", "description": "Resize an image to specified dimensions", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "width": {"type": "integer", "description": "Target width in pixels"}, "height": {"type": "integer", "description": "Target height in pixels"}, "keep_ratio": {"type": "boolean", "default": True}}, "required": ["input_path", "output_path", "width", "height"]}},
    {"name": "compress_image", "description": "Compress image to reduce file size", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "quality": {"type": "integer", "description": "Quality 1-100 (lower = smaller)", "default": CONST_75}}, "required": ["input_path", "output_path"]}},
    {"name": "extract_metadata", "description": "Extract EXIF and metadata from an image", "parameters": {"type": "object", "properties": {"input_path": {"type": "string", "description": "Image file path"}}, "required": ["input_path"]}},
    {"name": "convert_video", "description": "Convert video format using ffmpeg", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "codec": {"type": "string", "description": "Video codec (libx264, libx265, libvpx)", "default": "libx264"}}, "required": ["input_path", "output_path"]}},
    {"name": "trim_video", "description": "Trim video to a time range", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "start": {"type": "string", "description": "Start time (HH:MM:SS or seconds)"}, "end": {"type": "string", "description": "End time (HH:MM:SS or seconds)"}}, "required": ["input_path", "output_path", "start", "end"]}},
    {"name": "extract_audio", "description": "Extract audio track from video", "parameters": {"type": "object", "properties": {"input_path": {"type": "string", "description": "Video file"}, "output_path": {"type": "string", "description": "Audio file path (e.g. output.mp3)"}}, "required": ["input_path", "output_path"]}},
    {"name": "convert_audio", "description": "Convert audio format using ffmpeg", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "bitrate": {"type": "string", "description": "Audio bitrate (e.g. 128k, 320k)", "default": "128k"}}, "required": ["input_path", "output_path"]}},
    {"name": "generate_thumbnail", "description": "Generate a thumbnail from a video or image", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "time": {"type": "string", "description": "Timestamp for video thumbnail (default 00:00:01)"}, "width": {"type": "integer", "default": CONST_320}}, "required": ["input_path", "output_path"]}},
    {"name": "watermark_image", "description": "Add a text watermark to an image", "parameters": {"type": "object", "properties": {"input_path": {"type": "string"}, "output_path": {"type": "string"}, "text": {"type": "string", "description": "Watermark text"}, "position": {"type": "string", "enum": ["top-left", "top-right", "bottom-left", "bottom-right", "center"], "default": "bottom-right"}, "opacity": {"type": "integer", "description": "Opacity 0-255", "default": CONST_128}}, "required": ["input_path", "output_path", "text"]}},
]

functions = {}

async def _run_cmd(cmd, timeout=120):
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    return proc.returncode, stdout.decode(errors="ignore").strip()

def _require_pillow():
    try:
        from PIL import Image, ImageDraw, ImageFont
        return Image, ImageDraw, ImageFont
    except ImportError:
        raise RuntimeError("Pillow not installed. Run: pip install Pillow")

async def convert_image(args):
    try:
        Image, _, _ = _require_pillow()
        inp = args["input_path"]
        out = args["output_path"]
        fmt = args["format"]
        img = Image.open(inp)
        if fmt == "JPEG" and img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(out, format=fmt, quality=95)
        return json.dumps({"success": True, "input": inp, "output": out, "format": fmt, "size": pathlib.Path(out).stat().st_size})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def resize_image(args):
    try:
        Image, _, _ = _require_pillow()
        inp = args["input_path"]
        out = args["output_path"]
        w, h = args["width"], args["height"]
        keep = args.get("keep_ratio", True)
        img = Image.open(inp)
        if keep:
            img.thumbnail((w, h), Image.LANCZOS)
        else:
            img = img.resize((w, h), Image.LANCZOS)
        img.save(out)
        return json.dumps({"success": True, "output": out, "width": img.width, "height": img.height})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def compress_image(args):
    try:
        Image, _, _ = _require_pillow()
        inp = args["input_path"]
        out = args["output_path"]
        quality = args.get("quality", CONST_75)
        img = Image.open(inp)
        if img.mode == "RGBA":
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=quality, optimize=True)
        orig = pathlib.Path(inp).stat().st_size
        comp = pathlib.Path(out).stat().st_size
        return json.dumps({"success": True, "output": out, "original_bytes": orig, "compressed_bytes": comp, "reduction": f"{(1-comp/orig)*100:.1f}%"})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def extract_metadata(args):
    try:
        from PIL import Image
        from PIL.ExifTags import TAGS
        inp = args["input_path"]
        img = Image.open(inp)
        meta = {"format": img.format, "mode": img.mode, "width": img.width, "height": img.height, "size": pathlib.Path(inp).stat().st_size}
        exif_data = img.getexif()
        if exif_data:
            readable = {}
            for tag_id, val in exif_data.items():
                tag_name = TAGS.get(tag_id, tag_id)
                try:
                    readable[str(tag_name)] = str(val)[:200]
                except Exception:
                    pass
            meta["exif"] = readable
        return json.dumps({"success": True, "metadata": meta})
    except Exception as e:
        return json.dumps({"error": str(e)})

async def convert_video(args):
    inp = args["input_path"]
    out = args["output_path"]
    codec = args.get("codec", "libx264")
    code, output = await _run_cmd(["ffmpeg", "-y", "-i", inp, "-c:v", codec, "-c:a", "copy", out], timeout=CONST_600)
    return json.dumps({"success": code == 0, "output": out, "log": output[-CONST_2000:]})

async def trim_video(args):
    inp = args["input_path"]
    out = args["output_path"]
    start = args["start"]
    end = args["end"]
    code, output = await _run_cmd(["ffmpeg", "-y", "-i", inp, "-ss", start, "-to", end, "-c", "copy", out], timeout=CONST_600)
    return json.dumps({"success": code == 0, "output": out, "log": output[-CONST_2000:]})

async def extract_audio(args):
    inp = args["input_path"]
    out = args["output_path"]
    code, output = await _run_cmd(["ffmpeg", "-y", "-i", inp, "-vn", "-acodec", "copy", out], timeout=CONST_300)
    return json.dumps({"success": code == 0, "output": out, "log": output[-CONST_2000:]})

async def convert_audio(args):
    inp = args["input_path"]
    out = args["output_path"]
    bitrate = args.get("bitrate", "128k")
    code, output = await _run_cmd(["ffmpeg", "-y", "-i", inp, "-b:a", bitrate, out], timeout=CONST_300)
    return json.dumps({"success": code == 0, "output": out, "log": output[-CONST_2000:]})

async def generate_thumbnail(args):
    inp = args["input_path"]
    out = args["output_path"]
    width = args.get("width", CONST_320)
    ext = pathlib.Path(inp).suffix.lower()
    if ext in (".mp4", ".avi", ".mov", ".mkv", ".webm"):
        time_pos = args.get("time", "00:00:01")
        code, output = await _run_cmd(["ffmpeg", "-y", "-i", inp, "-ss", time_pos, "-vframes", "1", "-vf", f"scale={width}:-1", out], timeout=60)
        return json.dumps({"success": code == 0, "output": out})
    else:
        try:
            Image, _, _ = _require_pillow()
            img = Image.open(inp)
            img.thumbnail((width, width), Image.LANCZOS)
            img.save(out)
            return json.dumps({"success": True, "output": out, "width": img.width, "height": img.height})
        except Exception as e:
            return json.dumps({"error": str(e)})

async def watermark_image(args):
    try:
        Image, ImageDraw, ImageFont = _require_pillow()
        inp = args["input_path"]
        out = args["output_path"]
        text = args["text"]
        position = args.get("position", "bottom-right")
        opacity = args.get("opacity", CONST_128)
        img = Image.open(inp).convert("RGBA")
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        try:
            font = ImageFont.truetype("arial.ttf", max(16, img.width // 20))
        except Exception:
            font = ImageFont.load_default()
        bbox = draw.textbbox((0, 0), text, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        margin = 10
        positions = {
            "top-left": (margin, margin),
            "top-right": (img.width - tw - margin, margin),
            "bottom-left": (margin, img.height - th - margin),
            "bottom-right": (img.width - tw - margin, img.height - th - margin),
            "center": ((img.width - tw) // 2, (img.height - th) // 2),
        }
        pos = positions.get(position, positions["bottom-right"])
        draw.text(pos, text, fill=(CONST_255, CONST_255, CONST_255, opacity), font=font)
        result = Image.alpha_composite(img, overlay).convert("RGB")
        result.save(out)
        return json.dumps({"success": True, "output": out, "position": position})
    except Exception as e:
        return json.dumps({"error": str(e)})

functions = {
    "convert_image": convert_image,
    "resize_image": resize_image,
    "compress_image": compress_image,
    "extract_metadata": extract_metadata,
    "convert_video": convert_video,
    "trim_video": trim_video,
    "extract_audio": extract_audio,
    "convert_audio": convert_audio,
    "generate_thumbnail": generate_thumbnail,
    "watermark_image": watermark_image,
}
