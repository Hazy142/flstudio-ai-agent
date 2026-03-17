"""OmniParser V2 FastAPI server for UI element detection.

Runs as a microservice on GCP (GCE with L4 GPU). Accepts screenshots
and returns detected UI elements with bounding boxes, labels, and types.
"""

from __future__ import annotations

import base64
import io
import logging
import sys
import time
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from PIL import Image
from pydantic import BaseModel, Field

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)-20s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("omniparser-server")

# ---------------------------------------------------------------------------
# OmniParser wrapper
# ---------------------------------------------------------------------------

# TODO: Replace this stub with the real OmniParser import once running
# inside the Docker container where OmniParser is installed.
#
# The real import path (after cloning into /app/omniparser):
#   sys.path.insert(0, "/app/omniparser")
#   from omni_parse import OmniParser
#
# The OmniParser class exposes:
#   parser = OmniParser(config)
#   result = parser.parse(image)  # PIL.Image -> dict with 'elements'

_omniparser = None


class OmniParserStub:
    """Stub that mimics the OmniParser interface for development/testing.

    Replace with the real OmniParser once deployed with GPU and model weights.
    """

    def __init__(self, weights_dir: str = "/app/weights") -> None:
        self.weights_dir = weights_dir
        logger.info("OmniParser stub initialised (weights_dir=%s)", weights_dir)

    def parse(self, image: Image.Image) -> dict:
        """Parse a screenshot and return detected UI elements.

        TODO: Replace with real OmniParser call:
            sys.path.insert(0, "/app/omniparser")
            from omni_parse import OmniParser
            parser = OmniParser(weights_dir=self.weights_dir)
            result = parser.parse(image)
            return result

        The real OmniParser returns a dict like:
            {
                "elements": [
                    {
                        "type": "button",
                        "label": "Play",
                        "bbox": [x1, y1, x2, y2],  # pixel coords
                        "confidence": 0.95,
                    },
                    ...
                ]
            }
        """
        w, h = image.size
        logger.warning("Using OmniParser STUB — returning empty results")
        return {
            "elements": [],
            "image_size": [w, h],
        }


def _load_omniparser() -> OmniParserStub:
    """Load OmniParser models. Tries the real parser first, falls back to stub."""
    try:
        sys.path.insert(0, "/app/omniparser")
        from omni_parse import OmniParser  # type: ignore[import-not-found]

        parser = OmniParser(weights_dir="/app/weights")
        logger.info("Loaded real OmniParser V2 with GPU support")
        return parser  # type: ignore[return-value]
    except Exception as exc:
        logger.warning("Could not load real OmniParser (%s), using stub", exc)
        return OmniParserStub()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ParseElement(BaseModel):
    id: int
    type: str
    label: str
    bbox: list[int]
    confidence: float


class ParseResponse(BaseModel):
    elements: list[ParseElement]
    image_size: list[int]
    parse_time_ms: float


class Base64Request(BaseModel):
    image: str = Field(..., description="Base64-encoded PNG/JPEG image")
    return_labels: bool = True


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _omniparser
    logger.info("Loading OmniParser V2 models...")
    _omniparser = _load_omniparser()
    logger.info("OmniParser ready")
    yield
    logger.info("Shutting down OmniParser server")


app = FastAPI(
    title="OmniParser V2",
    description="UI element detection microservice for DAWMind",
    version="1.0.0",
    lifespan=lifespan,
)


def _run_parse(image: Image.Image) -> ParseResponse:
    """Run OmniParser on a PIL image and return structured response."""
    start = time.perf_counter()
    result = _omniparser.parse(image)
    elapsed_ms = (time.perf_counter() - start) * 1000

    elements = []
    for idx, elem in enumerate(result.get("elements", [])):
        bbox_raw = elem.get("bbox", [0, 0, 0, 0])
        bbox = [int(round(v)) for v in bbox_raw]
        elements.append(
            ParseElement(
                id=idx,
                type=elem.get("type", "unknown"),
                label=elem.get("label", ""),
                bbox=bbox,
                confidence=round(elem.get("confidence", 0.0), 4),
            )
        )

    w, h = image.size
    return ParseResponse(
        elements=elements,
        image_size=[w, h],
        parse_time_ms=round(elapsed_ms, 1),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": _omniparser is not None,
    }


@app.post("/parse", response_model=ParseResponse)
async def parse_image(
    file: UploadFile | None = File(None),
    body: Base64Request | None = None,
):
    """Parse a screenshot and return detected UI elements.

    Accepts either:
    - Multipart file upload (field name: ``file``)
    - JSON body with base64-encoded image (field: ``image``)
    """
    image: Image.Image | None = None

    if file is not None:
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Empty file upload")
        image = Image.open(io.BytesIO(data)).convert("RGB")
    elif body is not None:
        try:
            decoded = base64.b64decode(body.image)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid base64 image data")
        image = Image.open(io.BytesIO(decoded)).convert("RGB")
    else:
        raise HTTPException(
            status_code=400,
            detail="Provide an image via multipart upload (field 'file') or JSON body (field 'image')",
        )

    if _omniparser is None:
        raise HTTPException(status_code=503, detail="OmniParser models not loaded")

    return _run_parse(image)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")
