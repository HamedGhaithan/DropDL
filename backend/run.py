import os
import sys
import uvicorn
from app.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "17321")),
        reload=False,
        **({"log_config": None} if getattr(sys, "frozen", False) else {}),
    )
