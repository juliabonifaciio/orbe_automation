"""Validação e medição de qualidade de imagem (OpenCV)."""
import cv2
import numpy as np


class ImageError(Exception):
    pass


def validate(data: bytes, filename: str, cfg) -> dict:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext not in cfg["ALLOWED_EXT"]:
        raise ImageError(f"formato '.{ext}' não suportado (use JPG, PNG ou WEBP)")
    if not data:
        raise ImageError("arquivo vazio")
    if len(data) > cfg["MAX_IMAGE_MB"] * 1024 * 1024:
        raise ImageError(f"arquivo excede o limite de {cfg['MAX_IMAGE_MB']:g} MB")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ImageError("arquivo corrompido ou não é uma imagem válida")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return {"ext": "jpg" if ext == "jpeg" else ext, "height": int(img.shape[0]), "width": int(img.shape[1]),
            "sharpness": float(cv2.Laplacian(gray, cv2.CV_64F).var()), "brightness": float(gray.mean())}
