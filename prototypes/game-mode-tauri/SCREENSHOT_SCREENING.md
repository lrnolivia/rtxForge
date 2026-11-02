# Local screenshot screening

The application screens unknown Steam Store images locally using the same
CPU-only detector on Windows and Linux. No OCR service, API key, or network
inference is required. The worker exits after each bounded batch; decisions
are cached by immutable image hash and screening version. Missing or failed
screening does not admit an unknown image into the picker or background.

The text-layout rules reject text-heavy promotional panels and small lettering
around the perimeter typical of HUDs. This is a heuristic: environmental signs
can be false positives, and icon-only interfaces can escape text detection.
Immutable hash corrections supplement detection; they are not required to add
an unfamiliar game. Clean-image guarantees are not possible with this detector.

## Dependency provenance

RapidOCR 3.9.2 engineering components: Copyright RapidOCR Authors, Apache-2.0.
PP-OCRv6 detection weights: derived from PaddleOCR, Copyright PaddlePaddle
Authors, Apache-2.0. Only PP-OCRv6_det_small.onnx is included and loaded.

Model SHA-256: `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f`.

Provenance and license statements:
- https://rapidai.github.io/RapidOCRDocs/main/en/model_licenses/
- https://github.com/RapidAI/RapidOCR/tree/v3.9.2
- https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE

ONNX Runtime is distributed under its MIT license. Python, OpenCV, NumPy,
Shapely and other included dependencies retain their own notices in the worker's
`notices` directory. PyInstaller's bootloader exception permits distribution
of the bundled application under its own license.

Build in an isolated environment using `screening-requirements.txt`, then run
`python build_screening.py --output <scratch>`. The resulting folder is copied
whole to `screening` beside the Game Mode executable.
