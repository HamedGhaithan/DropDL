"""Run the web version for development: python web/serve.py  (then open http://127.0.0.1:7860)."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("server.app:app", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "7860")),
                access_log=False, log_level="info")
