import time
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from dotenv import load_dotenv

from models import DrugSafetyRequest, DrugSafetyResponse
from cache import build_cache_key, get_cached, set_cached
from engine import analyze_drug_safety

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("EvoDoc Clinical Drug Safety Engine starting up...")
    logger.info("Ensure Ollama is running: ollama serve")
    yield
    logger.info("Shutting down...")

app = FastAPI(
    title="EvoDoc Clinical Drug Safety Engine",
    description="Checks drug interactions, allergy alerts, and condition contraindications using a local medical LLM.",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_ui():
    return FileResponse("static/dashboard.html")

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "EvoDoc Drug Safety Engine"}

@app.post("/check-safety", response_model=DrugSafetyResponse)
async def check_drug_safety(request: DrugSafetyRequest):
    start_time = time.time()

    cache_key = build_cache_key(
        proposed_medicines=request.proposed_medicines,
        current_medications=request.patient_history.current_medications,
        known_allergies=request.patient_history.known_allergies,
        conditions=request.patient_history.conditions,
    )

    cached_result = get_cached(cache_key)
    if cached_result is not None:
        logger.info(f"Cache HIT for key: {cache_key[:16]}...")
        cached_result["cache_hit"] = True
        cached_result["processing_time_ms"] = int((time.time() - start_time) * 1000)
        return JSONResponse(content=cached_result)

    logger.info(f"Cache MISS — running full analysis for: {request.proposed_medicines}")
    result = await analyze_drug_safety(request, cache_hit=False)

    set_cached(cache_key, result)

    return JSONResponse(content=result)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "detail": "An unexpected error occurred. Please try again.",
            "source": "error_handler"
        }
    )