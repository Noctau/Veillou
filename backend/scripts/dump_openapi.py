"""Сохраняет OpenAPI-схему без запуска сервера: python -m scripts.dump_openapi <path>"""

import json
import sys
from pathlib import Path

from app.main import app

if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
    out.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n")
    print(f"OpenAPI -> {out}")
