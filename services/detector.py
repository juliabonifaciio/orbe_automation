"""Detectores de visão computacional substituíveis. Nunca devolve detecções simuladas."""
from pathlib import Path

CATEGORIES = {
    "vehicle": {"car", "truck", "bus", "motorcycle", "carro", "caminhao", "caminhão", "onibus", "ônibus", "moto", "vehicle", "veiculo", "veículo"},
    "person": {"person", "pessoa"},
    "fire": {"fire", "fogo", "flame", "smoke", "incendio", "incêndio", "fumaca", "fumaça"},
    "rollover": {"rollover", "capotamento", "overturned"},
    "collision": {"collision", "crash", "accident", "colisao", "colisão", "acidente"},
}
CAT_NAME = {"vehicle": "veículos", "person": "pessoas", "fire": "indício de incêndio",
            "rollover": "indício de capotamento", "collision": "indício de colisão"}


def summarize(dets):
    out = {}
    for d in dets:
        for cat, names in CATEGORIES.items():
            if d["label"].lower() in names:
                s = out.setdefault(cat, {"count": 0, "max": 0.0})
                s["count"] += 1
                s["max"] = max(s["max"], d["conf"])
    return out


class Detector:
    name = "base"
    reason = ""

    def available(self):
        return False

    def detect(self, path):
        raise NotImplementedError


class UnavailableDetector(Detector):
    name = "indisponível"

    def __init__(self, reason):
        self.reason = reason


class YoloDetector(Detector):
    name = "YOLO (Ultralytics)"

    def __init__(self, model_path):
        self.model_path, self._model = model_path, None

    def available(self):
        return Path(self.model_path).exists() or _is_bare(self.model_path)

    def detect(self, path):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self.model_path)
        r = self._model(str(path), verbose=False)[0]
        return [{"label": str(r.names[int(b.cls)]), "conf": round(float(b.conf), 3)} for b in r.boxes]


def _is_bare(p):
    """Nome simples de modelo do Ultralytics (ex.: yolo11s.pt): a biblioteca baixa sozinha se houver internet."""
    return p.endswith(".pt") and "/" not in p and "\\" not in p


def get_detector(cfg):
    p = cfg["MODEL_PATH"]
    if not Path(p).exists() and not _is_bare(p):
        return UnavailableDetector(f"pesos YOLO não encontrados em '{p}' — coloque o .pt em models/orbe.pt ou ajuste YOLO_MODEL no .env")
    try:
        import ultralytics  # noqa: F401
    except ImportError:
        return UnavailableDetector("biblioteca ultralytics não instalada")
    return YoloDetector(p)
