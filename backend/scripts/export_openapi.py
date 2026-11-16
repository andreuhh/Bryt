"""Write the OpenAPI schema used to generate the frontend TypeScript types.

.venv/bin/python -m scripts.export_openapi   (then: cd ../frontend && npm run gen:api)
"""

import json
from pathlib import Path

from app.main import app

TARGET = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"

if __name__ == "__main__":
    TARGET.write_text(json.dumps(app.openapi(), indent=1, ensure_ascii=False) + "\n")
    print(f"wrote {TARGET}")
