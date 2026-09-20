from fastapi import FastAPI

app = FastAPI(title="ml-samd-validator")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
