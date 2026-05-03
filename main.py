from fastapi import FastAPI
import uvicorn

app = FastAPI(title="AI Resume Evolver API")


@app.get("/health")
async def health_check():
    return {"status": "online", "port": 8001, "engine": "LangGraph"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
