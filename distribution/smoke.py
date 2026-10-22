"""Import native services and offline tokenizer using only packaged dependencies."""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
mode = sys.argv[1]
if mode == 'intake':
    sys.path.insert(0, str(ROOT / 'intake-agent'))
    from local_intake.nvidia_preparation_app import app
    import cv2
    import riva.client
    import grpc
    assert app.version == '5.0.0'
    detector = cv2.FaceDetectorYN.create(str(ROOT / '.runtime/tools/yunet.onnx'), '', (320, 320))
    assert detector is not None
    sys.path.insert(0, str(ROOT / 'integration/vision'))
    import media_bridge
    assert media_bridge.app
    sys.path.insert(0, str(ROOT / 'integration/portal'))
    import app as portal
    assert portal.app
elif mode == 'vision':
    sys.path.insert(0, str(ROOT / 'vision-agent/Vision_Agent/02_VISION_PROJECT'))
    from agents.vision.api import app
    assert app
elif mode == 'knowledge':
    sys.path.insert(0, str(ROOT / 'integration/knowledge'))
    from common import configure, prepare, RUNTIME
    prepare(); configure()
    sys.path.insert(0, str(RUNTIME))
    from api.knowledge_agent import app
    from transformers import AutoTokenizer
    from qdrant_client import QdrantClient
    tokenizer = AutoTokenizer.from_pretrained('BAAI/bge-m3', local_files_only=True)
    assert len(tokenizer.encode('Un probleme municipal.')) > 1
    client = QdrantClient(':memory:')
    client.close()
else:
    raise SystemExit('Unknown smoke mode')
assert str(ROOT) in sys.executable
assert Path(sys.base_prefix).is_relative_to(ROOT / 'vendor/python')
assert Path(os.__file__).is_relative_to(ROOT / 'vendor/python')
print(mode + ': native imports and offline resources OK; no model calls.')
