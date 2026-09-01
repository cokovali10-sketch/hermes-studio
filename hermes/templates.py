"""Project templates for quick scaffolding."""
from hermes.core import WORKSPACE_DIR
from hermes.bus import bus

TEMPLATES = {
    "react-ts": {
        "name": "React + TypeScript + Vite",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "private": true,\n  "version": "0.0.0",\n  "type": "module",\n  "scripts": {\n    "dev": "vite",\n    "build": "tsc && vite build",\n    "preview": "vite preview"\n  },\n  "dependencies": {\n    "react": "^18.2.0",\n    "react-dom": "^18.2.0"\n  },\n  "devDependencies": {\n    "@types/react": "^18.2.0",\n    "@types/react-dom": "^18.2.0",\n    "@vitejs/plugin-react": "^4.2.0",\n    "typescript": "^5.3.0",\n    "vite": "^5.0.0"\n  }\n}',
            "tsconfig.json": '{\n  "compilerOptions": {\n    "target": "ES2020",\n    "useDefineForClassFields": true,\n    "lib": ["ES2020", "DOM", "DOM.Iterable"],\n    "module": "ESNext",\n    "skipLibCheck": true,\n    "moduleResolution": "bundler",\n    "allowImportingTsExtensions": true,\n    "resolveJsonModule": true,\n    "isolatedModules": true,\n    "noEmit": true,\n    "jsx": "react-jsx",\n    "strict": true\n  },\n  "include": ["src"]\n}',
            "vite.config.ts": 'import { defineConfig } from "vite"\nimport react from "@vitejs/plugin-react"\n\nexport default defineConfig({\n  plugins: [react()],\n})',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n  <head>\n    <meta charset="UTF-8" />\n    <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n    <title>{{name}}</title>\n  </head>\n  <body>\n    <div id="root"></div>\n    <script type="module" src="/src/main.tsx"></script>\n  </body>\n</html>',
            "src/main.tsx": 'import React from "react"\nimport ReactDOM from "react-dom/client"\nimport App from "./App"\n\nReactDOM.createRoot(document.getElementById("root")!).render(\n  <React.StrictMode>\n    <App />\n  </React.StrictMode>,\n)',
            "src/App.tsx": 'export default function App() {\n  return (\n    <div style={{ padding: "2rem", fontFamily: "system-ui" }}>\n      <h1>{{name}}</h1>\n      <p>React + TypeScript is ready!</p>\n    </div>\n  )\n}',
            "src/vite-env.d.ts": '/// <reference types="vite" />',
        },
        "install": "npm install",
        "dev": "npm run dev",
    },
    "python-fastapi": {
        "name": "Python FastAPI",
        "files": {
            "requirements.txt": "fastapi==0.108.0\nuvicorn==0.25.0\npydantic==2.5.0",
            "main.py": 'from fastapi import FastAPI\nfrom pydantic import BaseModel\n\napp = FastAPI(title="{{name}}")\n\nclass Item(BaseModel):\n    name: str\n    price: float\n\n@app.get("/")\ndef root():\n    return {"message": "Hello from {{name}}"}\n\n@app.get("/items")\ndef list_items():\n    return [{"name": "Item 1", "price": 9.99}]\n\n@app.post("/items")\ndef create_item(item: Item):\n    return {"created": item.name, "price": item.price}\n\nif __name__ == "__main__":\n    import uvicorn\n    uvicorn.run(app, host="0.0.0.0", port=8000)',
            "README.md": "# {{name}}\n\nFastAPI project.\n\n```bash\npip install -r requirements.txt\npython main.py\n```\n\nOpen: http://localhost:8000/docs",
        },
        "install": "pip install -r requirements.txt",
        "dev": "python main.py",
    },
    "node-express": {
        "name": "Node.js Express",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "version": "1.0.0",\n  "scripts": {\n    "start": "node server.js",\n    "dev": "node --watch server.js"\n  },\n  "dependencies": {\n    "express": "^4.18.0"\n  }\n}',
            "server.js": 'const express = require("express")\nconst app = express()\nconst PORT = process.env.PORT || 3000\n\napp.use(express.json())\n\napp.get("/", (req, res) => {\n  res.json({ message: "Hello from {{name}}" })\n})\n\napp.get("/api/health", (req, res) => {\n  res.json({ status: "ok", uptime: process.uptime() })\n})\n\napp.listen(PORT, () => {\n  console.log(`Server running on http://localhost:${PORT}`)\n})',
            "README.md": "# {{name}}\n\nExpress server.\n\n```bash\nnpm install\nnpm run dev\n```",
        },
        "install": "npm install",
        "dev": "npm run dev",
    },
    "static-html": {
        "name": "Static HTML/CSS/JS",
        "files": {
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>{{name}}</title>\n  <link rel="stylesheet" href="style.css" />\n</head>\n<body>\n  <div class="container">\n    <h1>{{name}}</h1>\n    <p>Static site is ready!</p>\n  </div>\n  <script src="script.js"></script>\n</body>\n</html>',
            "style.css": '* { box-sizing: border-box; margin: 0; padding: 0; }\nbody { font-family: system-ui; padding: 2rem; background: #0a0a0a; color: #fafafa; }\n.container { max-width: 800px; margin: 0 auto; }\nh1 { font-size: 2rem; margin-bottom: 1rem; }',
            "script.js": 'console.log("{{name}} loaded!")',
        },
        "install": None,
        "dev": None,
    },
    "vanilla-js": {
        "name": "Vanilla JavaScript App",
        "files": {
            "package.json": '{\n  "name": "{{name}}",\n  "version": "1.0.0",\n  "scripts": {\n    "dev": "npx live-server --port=3000"\n  }\n}',
            "index.html": '<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8" />\n  <meta name="viewport" content="width=device-width, initial-scale=1.0" />\n  <title>{{name}}</title>\n  <link rel="stylesheet" href="style.css" />\n</head>\n<body>\n  <div id="app"></div>\n  <script type="module" src="main.js"></script>\n</body>\n</html>',
            "main.js": 'import { createApp } from "./app.js"\ndocument.getElementById("app").appendChild(createApp())',
            "app.js": 'export function createApp() {\n  const div = document.createElement("div")\n  div.innerHTML = `<h1>{{name}}</h1><p>Vanilla JS is ready!</p>`\n  return div\n}',
            "style.css": '* { box-sizing: border-box; margin: 0; padding: 0; }\nbody { font-family: system-ui; padding: 2rem; background: #0a0a0a; color: #fafafa; }\nh1 { font-size: 2rem; margin-bottom: 1rem; }',
        },
        "install": None,
        "dev": "npx live-server --port=3000",
    },
}


async def tool_list_templates() -> dict:
    templates = []
    for key, tpl in TEMPLATES.items():
        templates.append({
            "id": key,
            "name": tpl["name"],
            "files": list(tpl["files"].keys()),
            "install": tpl.get("install"),
            "dev": tpl.get("dev"),
        })
    return {"templates": templates, "success": True}


async def tool_scaffold_project(template: str, name: str) -> dict:
    if template not in TEMPLATES:
        return {"error": f"Unknown template: {template}", "valid": list(TEMPLATES.keys()), "success": False}

    tpl = TEMPLATES[template]
    project_dir = WORKSPACE_DIR / name

    if project_dir.exists():
        return {"error": f"Directory already exists: {name}", "success": False}

    project_dir.mkdir(parents=True, exist_ok=True)
    created_files = []

    for file_path, content in tpl["files"].items():
        content = content.replace("{{name}}", name)
        target = project_dir / file_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        created_files.append(file_path)

    bus.emit("tool.scaffold", {"template": template, "name": name, "files": len(created_files)})

    return {
        "success": True,
        "project": name,
        "template": template,
        "files": created_files,
        "install": tpl.get("install"),
        "dev": tpl.get("dev"),
        "path": str(project_dir),
    }
