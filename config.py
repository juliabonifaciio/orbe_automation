"""Configuração do ORBE. Valores podem ser sobrescritos pelo arquivo .env."""
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent


def _load_env():
    f = BASE / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


_load_env()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "orbe-dev-troque-em-producao")
    DATABASE = os.getenv("ORBE_DB", str(BASE / "data" / "orbe.db"))
    UPLOAD_DIR = str(BASE / "uploads")
    REPORT_DIR = str(BASE / "reports")
    MODEL_PATH = os.getenv("YOLO_MODEL", str(BASE / "models" / "orbe.pt"))
    # Caminhos relativos no .env (ex.: models/meu.pt) são resolvidos a partir da pasta do projeto
    if "/" in MODEL_PATH.replace("\\", "/") and not os.path.isabs(MODEL_PATH):
        MODEL_PATH = str(BASE / MODEL_PATH)
    MAX_IMAGE_MB = float(os.getenv("MAX_IMAGE_MB", "8"))
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024
    ALLOWED_EXT = {"jpg", "jpeg", "png", "webp"}
    # Critérios de triagem configuráveis
    TRIAGE = {"low_conf": 0.45, "victims_high": 3, "vehicles_medium": 2, "vehicles_high": 5}
    # IA de texto (opcional): sem chave => relatório por template de contingência
    LLM_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")
    LLM_MODEL = os.getenv("LLM_MODEL", "claude-sonnet-5-5")
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "60"))
    # Pontos de injeção (usados nos testes): DETECTOR, LLM_FN
