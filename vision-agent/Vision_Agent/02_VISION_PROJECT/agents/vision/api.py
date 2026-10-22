"""Local POST /vision interface using the same runner as the experiments."""

import argparse
import hashlib
from io import BytesIO
from threading import Lock
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from PIL import Image, UnidentifiedImageError

from .run import ROOT, analyze_image
from .schema import VisionObservation

app = FastAPI(title="Municipal Vision", version="1.0")
model_lock = Lock()
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000


class VisionResponse(VisionObservation):
    """The validated observation, its caller's report ID and saved run ID."""

    report_id: str
    run_id: str


def validate_upload(data):
    """Check actual JPEG/PNG content and dimensions, not the supplied filename."""
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Supply an image between 1 byte and 10 MiB.")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in ("JPEG", "PNG"):
                raise HTTPException(415, "Only JPEG and PNG images are accepted.")
            if image.width * image.height > MAX_PIXELS or getattr(image, "n_frames", 1) != 1:
                raise HTTPException(422, "Use one still image with at most 20 million pixels.")
            extension = ".jpg" if image.format == "JPEG" else ".png"
            image.verify()
        # Decode pixels too: some truncated JPEGs pass the header verification.
        with Image.open(BytesIO(data)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(422, "The uploaded image cannot be decoded.") from error
    return extension


@app.post("/vision", response_model=VisionResponse)
def vision(
    image: Annotated[UploadFile, File()],
    report_id: Annotated[str, Form(min_length=1, max_length=100)],
    description: Annotated[str | None, Form(max_length=2000)] = None,
):
    """Validate an upload, call local Ollama and return the actual observation.

    One request runs at a time on the local prototype. Errors are returned as
    errors; a failed model call is never replaced with a made-up observation.
    """
    report_id = report_id.strip()
    if not report_id:
        raise HTTPException(422, "report_id cannot be blank.")
    description = description.strip() or None if description else None
    try:
        data = image.file.read(MAX_BYTES + 1)
    finally:
        image.file.close()
    extension = validate_upload(data)
    if not model_lock.acquire(blocking=False):
        raise HTTPException(503, "The local model is busy; try again after this request finishes.")
    try:
        digest = hashlib.sha256(data).hexdigest()
        folder = ROOT / "evaluation/vision/uploads"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (digest + extension)
        # Never use report IDs or user filenames as filesystem paths.
        if not path.exists():
            path.write_bytes(data)
        photo = {"sha256": digest, "scene_group": "upload-" + digest,
                 "split": "http_input", "file": path.relative_to(ROOT).as_posix()}
        args = argparse.Namespace(
            image_id="UPLOAD-" + digest[:12], model="qwen2.5vl:3b", prompt_version="v11",
            description=description, structured=True, timeout=600, context_size=8192,
            severity_rubric=True, report_id=report_id,
        )
        result, _ = analyze_image(args, photo, data)
    finally:
        model_lock.release()
    if result["status"] != "completed":
        raise HTTPException(502, {"message": "Model output failed validation or inference.",
                                  "run_id": result["run_id"], "error_type": result["error_type"]})
    return {"report_id": report_id, "run_id": result["run_id"], **result["observation"]}
