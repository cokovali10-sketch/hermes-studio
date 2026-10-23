"""Vision tools — analyze screenshots, compare images, generate 3D scenes."""
from __future__ import annotations

from hermes.modules.vision.analysis import (
    analyze_ui_screenshot,
    compare_screenshots,
    extract_text_from_image,
)
from hermes.modules.vision.threejs_gen import generate_threejs_scene, create_3d_object


async def tool_analyze_ui_screenshot(image_b64: str) -> dict:
    return await analyze_ui_screenshot(image_b64)


async def tool_compare_screenshots(img1_b64: str, img2_b64: str) -> dict:
    return await compare_screenshots(img1_b64, img2_b64)


async def tool_generate_threejs_scene(description: str) -> dict:
    return await generate_threejs_scene(description)


async def tool_create_3d_object(object_type: str = "cube", color: str = "4fc3f7",
                                 size: float = 1.0, wireframe: bool = False) -> dict:
    return await create_3d_object(object_type, color, size, wireframe)


VISION_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "analyze_ui_screenshot",
            "description": "Analyze a base64-encoded screenshot for UI element detection, color analysis, and layout info.",
            "parameters": {
                "type": "object",
                "properties": {
                    "image_b64": {"type": "string", "description": "Base64-encoded image data"},
                },
                "required": ["image_b64"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compare_screenshots",
            "description": "Compare two base64-encoded screenshots and return pixel differences.",
            "parameters": {
                "type": "object",
                "properties": {
                    "img1_b64": {"type": "string", "description": "First image (base64)"},
                    "img2_b64": {"type": "string", "description": "Second image (base64)"},
                },
                "required": ["img1_b64", "img2_b64"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_threejs_scene",
            "description": "Generate a complete HTML file with an embedded Three.js 3D scene.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description": {"type": "string", "description": "Description of the scene (e.g. 'rotating red cube', 'blue sphere')"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_3d_object",
            "description": "Generate a Three.js HTML file with a specific 3D object.",
            "parameters": {
                "type": "object",
                "properties": {
                    "object_type": {"type": "string", "enum": ["cube", "sphere", "plane"], "default": "cube"},
                    "color": {"type": "string", "description": "Hex color without # (e.g. '4fc3f7')", "default": "4fc3f7"},
                    "size": {"type": "number", "default": 1.0},
                    "wireframe": {"type": "boolean", "default": False},
                },
                "required": [],
            },
        },
    },
]

VISION_TOOL_MAP = {
    "analyze_ui_screenshot": tool_analyze_ui_screenshot,
    "compare_screenshots": tool_compare_screenshots,
    "generate_threejs_scene": tool_generate_threejs_scene,
    "create_3d_object": tool_create_3d_object,
}
