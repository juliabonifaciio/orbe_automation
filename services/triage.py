"""Regras de triagem operacional (sugestão — nunca diagnóstico clínico)."""
from .detector import summarize

LABEL = {"ALTA": "Alta", "MEDIA": "Média", "VERIFICACAO": "Necessita de verificação",
         "SEM_INDICACAO": "Sem indicação operacional identificada"}


def pendencias(occ, has_image):
    bloq, info = [], []
    for k, n in (("rodovia", "rodovia"), ("km", "quilômetro"), ("sentido", "sentido")):
        if not occ.get(k):
            bloq.append(f"Localização incompleta: {n} não informado(a)")
    if occ.get("n_veiculos") is None:
        info.append("Quantidade de veículos não informada")
    if occ.get("n_vitimas") is None:
        info.append("Quantidade de vítimas não informada")
    if occ.get("presos") in (None, "nao_informado"):
        info.append("Existência de pessoas presas não informada")
    if not has_image:
        info.append("Nenhuma imagem enviada")
    return bloq, info


def classify(occ, ana, has_image, t):
    """Retorna (prioridade, motivos, bloqueantes, informativas)."""
    bloq, info = pendencias(occ, has_image)
    alta, media, ver = [], [], []
    dets = ana["detections"] if ana and ana["status"] == "ok" else []
    s = summarize(dets)
    for cat, nome in (("fire", "incêndio"), ("rollover", "capotamento")):
        if cat in s:
            c = s[cat]["max"]
            if c >= t["low_conf"]:
                alta.append(f"Regra 1: indício de {nome} na imagem (confiança {c:.2f}, não confirmado) — sujeito à revisão humana")
            else:
                ver.append(f"Regra 3: possível indício de {nome} com baixa confiança ({c:.2f}) — exige revisão humana")
    if occ.get("presos") == "sim":
        alta.append("Profissional informou pessoas presas")
    nv = occ.get("n_vitimas") or 0
    if nv >= t["victims_high"]:
        alta.append(f"Profissional informou {nv} vítimas")
    veic = max(occ.get("n_veiculos") or 0, s.get("vehicle", {}).get("count", 0))
    if veic >= t["vehicles_high"]:
        alta.append(f"{veic} veículos envolvidos")
    elif veic >= t["vehicles_medium"]:
        media.append(f"{veic} veículos envolvidos")
    if 0 < nv < t["victims_high"]:
        media.append(f"Profissional informou {nv} vítima(s)")
    if "person" in s:
        media.append("Pessoas detectadas na imagem (não indica, por si só, a existência de vítimas)")
    if dets and all(d["conf"] < t["low_conf"] for d in dets):
        ver.append("Regra 3: todas as detecções com baixa confiança — situação não confirmada")
    if ana and ana["status"] != "ok":
        ver.append("Análise automática da imagem indisponível — imagem requer verificação humana")
    if bloq:
        ver.append("Regra 2: localização incompleta — complementar antes da aprovação")
    pri = "ALTA" if alta else "MEDIA" if media else "VERIFICACAO" if (ver or bloq) else "SEM_INDICACAO"
    return pri, alta + media + ver, bloq, info
