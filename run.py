"""Build the React client when needed, then serve the complete local app."""

from pathlib import Path
import subprocess

from backend.server import DIST, ROOT, serve


if __name__ == "__main__":
    frontend = ROOT / "frontend"
    if not (DIST / "index.html").exists():
        if not (frontend / "node_modules").exists():
            subprocess.run(["npm", "install"], cwd=frontend, check=True)
        subprocess.run(["npm", "run", "build"], cwd=frontend, check=True)
    serve()
