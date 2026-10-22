"""Read verified retained bytes locally; deliberately not a new HTTP endpoint."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
import time

from PIL import Image

from .runtime import Settings, confined


def read_verified_image(path, settings=None):
    settings = settings or Settings()
    root = settings.root.resolve()
    path = confined(path, root/"safe")
    relative = path.relative_to(root/"safe")
    if len(relative.parts) != 2:
        raise ValueError("Unexpected processed-media path")
    token = relative.parts[0]
    if len(token)!=32 or any(c not in '0123456789abcdef' for c in token):
        raise ValueError("Invalid request token")
    receipt_path = root/"receipts"/(token+".json")
    if time.time()-receipt_path.stat().st_mtime >= settings.retention_seconds:
        raise ValueError("Processed media has expired")
    receipt=json.loads(receipt_path.read_text(encoding="utf-8"))
    evidence=receipt["processed_images"].get(str(path))
    data=path.read_bytes()
    if not evidence or not evidence.get('detector_completed') or not evidence.get('write_and_decode_verified') or hashlib.sha256(data).hexdigest()!=evidence.get('sha256'):
        raise ValueError("Processed-media evidence mismatch")
    with Image.open(BytesIO(data)) as image:
        image.verify()
    return data, {**evidence, "inference_mode": receipt.get("inference_mode", "UNKNOWN")}
