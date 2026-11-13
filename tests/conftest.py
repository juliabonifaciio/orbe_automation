import io
import sys
from pathlib import Path

import cv2
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app  # noqa: E402
from services.detector import Detector  # noqa: E402


class FakeDetector(Detector):
    name = "Detector falso (testes)"

    def __init__(self, dets=None, ok=True, boom=False):
        self.dets, self.ok, self.boom, self.reason = dets or [], ok, boom, "detector de teste indisponível"

    def available(self):
        return self.ok

    def detect(self, path):
        if self.boom:
            raise RuntimeError("explodiu")
        return self.dets


def jpg_bytes(noise=True):
    img = (np.random.randint(0, 255, (120, 160, 3), dtype=np.uint8) if noise else np.full((120, 160, 3), 128, np.uint8))
    return cv2.imencode(".jpg", img)[1].tobytes()


@pytest.fixture
def make_app(tmp_path):
    def _mk(**kw):
        cfg = {"TESTING": True, "DATABASE": str(tmp_path / "t.db"), "UPLOAD_DIR": str(tmp_path / "up"),
               "REPORT_DIR": str(tmp_path / "rep"), "DETECTOR": FakeDetector(), "LLM_FN": None, "LLM_API_KEY": ""}
        cfg.update(kw)
        return create_app(cfg)
    return _mk


@pytest.fixture
def app(make_app):
    return make_app()


@pytest.fixture
def client(app):
    return app.test_client()


FULL = {"profissional": "Ana Paramédica", "rodovia": "BR-116", "km": "150", "sentido": "Sul", "tipo": "Colisão",
        "n_veiculos": "2", "n_vitimas": "1", "presos": "nao", "apoio": "Guincho", "descricao": "Colisão traseira"}


def new_occ(client, **over):
    data = {**FULL, **over}
    r = client.post("/novo", data=data)
    assert r.status_code == 302
    return r.headers["Location"].rsplit("/", 1)[-1]


def analyze(client, oid, img=None, name="foto.jpg"):
    data = {"imagem": (io.BytesIO(img), name)} if img is not None else {}
    return client.post(f"/ocorrencia/{oid}/analisar", data=data, content_type="multipart/form-data", follow_redirects=True)
