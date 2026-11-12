import os

import uvicorn
from dotenv import load_dotenv

load_dotenv()

if __name__ == "__main__":
    dev = os.getenv("APP_ENV", "development").lower() != "production"
    uvicorn.run(
        "app.backend.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
        reload=dev,
        server_header=False,   # не сообщаем всем, на чём работаем
    )