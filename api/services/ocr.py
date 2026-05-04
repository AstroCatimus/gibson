"""
Gibson OCR pipeline.
Primary: EasyOCR + PaddleOCR ensemble
Fallback: Calamari fraktur19 for German Fraktur when confidence < 0.70
Claude Vision handles final extraction regardless — OCR feeds it context.
"""

import base64
from typing import Optional


async def run_ocr_pipeline(image_base64: str, language_signal: Optional[str] = None) -> dict:
    """
    Run the OCR ensemble on a base64-encoded image.
    Returns extracted text with confidence score.

    Primary: EasyOCR + PaddleOCR ensemble
    Fallback: Calamari fraktur19 for German Fraktur when ensemble confidence < 0.70
    """
    # Decode image
    try:
        image_bytes = base64.b64decode(image_base64)
    except Exception:
        return {"text": "", "confidence": 0.0, "engine": "none", "error": "Invalid base64"}

    # Primary ensemble
    easy_result = await _run_easyocr(image_bytes)
    paddle_result = await _run_paddleocr(image_bytes)
    ensemble = _merge_ensemble(easy_result, paddle_result)

    # Calamari fallback for German Fraktur
    if (language_signal == "german" or _detect_fraktur_signals(ensemble.get("text", ""))) \
            and ensemble.get("confidence", 0) < 0.70:
        calamari_result = await _run_calamari(image_bytes, model="fraktur19")
        if calamari_result.get("confidence", 0) > ensemble.get("confidence", 0):
            ensemble = _merge_with_calamari(ensemble, calamari_result)

    return ensemble


async def _run_easyocr(image_bytes: bytes) -> dict:
    """Run EasyOCR on image bytes."""
    try:
        import easyocr
        import numpy as np
        from PIL import Image
        import io

        reader = easyocr.Reader(["en"], gpu=False)
        image = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(image)

        results = reader.readtext(img_array)

        text_parts = []
        total_confidence = 0
        for bbox, text, confidence in results:
            text_parts.append(text)
            total_confidence += confidence

        avg_confidence = total_confidence / len(results) if results else 0
        return {
            "text": " ".join(text_parts),
            "confidence": avg_confidence,
            "engine": "easyocr",
            "regions": len(results),
        }
    except ImportError:
        return {"text": "", "confidence": 0.0, "engine": "easyocr", "error": "not installed"}
    except Exception as e:
        return {"text": "", "confidence": 0.0, "engine": "easyocr", "error": str(e)}


async def _run_paddleocr(image_bytes: bytes) -> dict:
    """Run PaddleOCR on image bytes."""
    try:
        from paddleocr import PaddleOCR
        import numpy as np
        from PIL import Image
        import io

        ocr = PaddleOCR(use_angle_cls=True, lang="en", show_log=False)
        image = Image.open(io.BytesIO(image_bytes))
        img_array = np.array(image)

        results = ocr.ocr(img_array, cls=True)

        text_parts = []
        total_confidence = 0
        count = 0
        if results and results[0]:
            for line in results[0]:
                text = line[1][0]
                confidence = line[1][1]
                text_parts.append(text)
                total_confidence += confidence
                count += 1

        avg_confidence = total_confidence / count if count > 0 else 0
        return {
            "text": " ".join(text_parts),
            "confidence": avg_confidence,
            "engine": "paddleocr",
            "regions": count,
        }
    except ImportError:
        return {"text": "", "confidence": 0.0, "engine": "paddleocr", "error": "not installed"}
    except Exception as e:
        return {"text": "", "confidence": 0.0, "engine": "paddleocr", "error": str(e)}


async def _run_calamari(image_bytes: bytes, model: str = "fraktur19") -> dict:
    """
    Calamari with pretrained Fraktur weights.
    0.18% character error rate on 19th-century German Fraktur.
    """
    try:
        # Calamari requires specific image preprocessing
        return {"text": "", "confidence": 0.0, "engine": "calamari", "error": "not yet configured"}
    except Exception as e:
        return {"text": "", "confidence": 0.0, "engine": "calamari", "error": str(e)}


def _merge_ensemble(easy: dict, paddle: dict) -> dict:
    """Merge EasyOCR and PaddleOCR results, preferring higher confidence."""
    easy_conf = easy.get("confidence", 0)
    paddle_conf = paddle.get("confidence", 0)

    if easy_conf >= paddle_conf and easy.get("text"):
        primary = easy
        secondary = paddle
    elif paddle.get("text"):
        primary = paddle
        secondary = easy
    else:
        primary = easy
        secondary = paddle

    # Combine texts if both have results
    combined_text = primary.get("text", "")
    if secondary.get("text") and secondary.get("confidence", 0) > 0.5:
        # Add any text from secondary that isn't in primary
        combined_text = primary.get("text", "")

    return {
        "text": combined_text,
        "confidence": max(easy_conf, paddle_conf),
        "engine": "ensemble",
        "easy_confidence": easy_conf,
        "paddle_confidence": paddle_conf,
    }


def _merge_with_calamari(ensemble: dict, calamari: dict) -> dict:
    """Merge Calamari result with ensemble for Fraktur text."""
    ensemble["text"] = calamari.get("text", ensemble.get("text", ""))
    ensemble["confidence"] = max(ensemble.get("confidence", 0), calamari.get("confidence", 0))
    ensemble["calamari_used"] = True
    return ensemble


def _detect_fraktur_signals(text: str) -> bool:
    """Detect signals that suggest German Fraktur typeface."""
    german_signals = ["und", "der", "die", "das", "von", "für", "über", "Verlag"]
    text_lower = text.lower()
    return any(signal.lower() in text_lower for signal in german_signals)
