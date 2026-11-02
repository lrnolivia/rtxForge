"""Portable, local screenshot screening. No OS OCR service or online inference."""
import hashlib
import json
from pathlib import Path
import sys

VERSION = 'text-layout-v1-090f04ab'
MODEL_SHA256 = '090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f'


def text_layout(boxes, width, height):
    """Reject promotional text and small HUD labels around the image perimeter.

    This is deliberately conservative. Environmental signs can be false positives;
    icons without detected lettering can be false negatives. Explicit corrections
    use immutable image hashes, rather than app IDs or current gallery ordering.
    """
    if width <= 0 or height <= 0:
        return {'clean': False, 'reason': 'invalid-image'}
    rectangles = []
    for box in boxes:
        xs, ys = [point[0] / width for point in box], [point[1] / height for point in box]
        left, top, right, bottom = min(xs), min(ys), max(xs), max(ys)
        if (right-left)*(bottom-top) < .000035:
            continue
        rectangles.append((left, top, right, bottom))
    if len(rectangles) >= 3:
        return {'clean': False, 'reason': 'text-heavy'}
    if any((r-l)*(b-t) > .025 for l, t, r, b in rectangles):
        return {'clean': False, 'reason': 'promotional-title'}
    if any(b-t < .1 and (l < .2 or r > .8 or t < .17 or b > .83)
           for l, t, r, b in rectangles):
        return {'clean': False, 'reason': 'edge-ui-label'}
    return {'clean': True, 'reason': 'screened'}


class Screener:
    def __init__(self):
        import rapidocr
        from rapidocr.utils.parse_parameters import ParseParams
        from rapidocr.ch_ppocr_det import TextDetector
        from rapidocr.utils.log import logger
        logger.setLevel('ERROR')
        root = Path(rapidocr.__file__).resolve().parent
        model = root / 'models/PP-OCRv6_det_small.onnx'
        if hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError('Screenshot model integrity check failed')
        cfg = ParseParams.load(root / 'config.yaml')
        cfg.Det.model_path = str(model)
        cfg.Det.engine_cfg = cfg.EngineConfig.onnxruntime
        cfg.Det.engine_cfg.intra_op_num_threads = 1
        cfg.Det.engine_cfg.inter_op_num_threads = 1
        cfg.Det.engine_cfg.enable_cpu_mem_arena = False
        cfg.Det.limit_side_len = 640
        # Instantiate only detection. Recognition/rotation models are not loaded.
        self.detector = TextDetector(cfg.Det)

    def screen(self, path):
        import cv2
        import numpy as np
        source = Path(path)
        if source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Screenshot exceeds screening limit')
        image = cv2.imdecode(np.frombuffer(source.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0]*image.shape[1] > 40_000_000:
            raise ValueError('Invalid screenshot for screening')
        if image.shape[1] > 1280:
            image = cv2.resize(image, (1280, max(1, round(image.shape[0]*1280/image.shape[1]))))
        result = self.detector(image)
        boxes = result.boxes.tolist() if result.boxes is not None else []
        return text_layout(boxes, image.shape[1], image.shape[0])


def main():
    # One bounded batch per process. No inference session or idle worker remains.
    request = json.loads(sys.stdin.buffer.read(64 * 1024))
    paths = request.get('paths', [])
    if not isinstance(paths, list) or len(paths) > 16 or any(not isinstance(p, str) for p in paths):
        raise ValueError('Invalid screenshot screening batch')
    screener = Screener()
    results = []
    for path in paths:
        try:
            results.append(screener.screen(path))
        except (OSError, ValueError):
            results.append({'clean': False, 'reason': 'unavailable'})
    print(json.dumps({'version': VERSION, 'results': results}, separators=(',', ':')))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'Screenshot screening failed: {type(error).__name__}: {error}', file=sys.stderr)
        print(json.dumps({'version': VERSION, 'results': [], 'error': 'Screenshot screening unavailable'}))
        sys.exit(1)
