"""Geração do relatório: seções estruturadas (determinísticas) + textos por IA ou template."""
import json
import time
import requests
from .detector import summarize, CAT_NAME
from .triage import LABEL

NI = "Não informado"
SYSTEM = ("Você redige relatórios operacionais de atendimento pré-hospitalar rodoviário. Use SOMENTE os fatos fornecidos. "
          "Não invente dados; campos vazios são 'Não informado'. Diferencie o que foi declarado pelo profissional do que foi "
          "inferido por visão computacional, apresente incertezas, não faça diagnóstico clínico nem afirme gravidade. "
          "Responda apenas JSON: {\"resumo\": \"...\", \"encaminhamento\": \"...\"}, linguagem objetiva e profissional.")


def fmt(v):
    return NI if v in (None, "") else str(v)


def image_text(ana, img):
    if not img:
        return "Nenhuma imagem enviada. Nenhuma análise visual foi realizada."
    q = []
    if img["sharpness"] < 60:
        q.append("imagem com baixa nitidez")
    if img["brightness"] < 40:
        q.append("imagem escura")
    qual = f" Qualidade: {', '.join(q)}." if q else ""
    if not ana or ana["status"] != "ok":
        motivo = ana["note"] if ana else "análise não executada"
        return f"Análise automática indisponível ({motivo}). Nenhuma detecção foi simulada; requer verificação humana.{qual}"
    s = summarize(ana["detections"])
    if not ana["detections"]:
        return f"Detector {ana['detector']} executado: nenhuma classe conhecida detectada. Isso não descarta riscos.{qual}"
    itens = [f"{d['label']} ({d['conf']:.2f})" for d in ana["detections"]]
    cats = "; ".join(f"{CAT_NAME[c]}: {v['count']} (conf. máx. {v['max']:.2f})" for c, v in s.items())
    return (f"Inferência de visão computacional ({ana['detector']}), não confirmada: {', '.join(itens)}. "
            f"{cats}. A confiança do modelo não confirma acidente nem gravidade.{qual}")


def build_facts(occ, prof, ana, img, pri, reasons, bloq, info):
    loc = f"{fmt(occ['rodovia'])}, km {fmt(occ['km'])}, sentido {fmt(occ['sentido'])}"
    dv = summarize(ana["detections"]).get("vehicle", {}).get("count") if ana and ana["status"] == "ok" else None
    veic = f"Declarado: {fmt(occ['n_veiculos'])}" + (f" | Detectados na imagem (inferência): {dv}" if dv else "")
    presos = {"sim": "Sim (informado pelo profissional)", "nao": "Não (informado pelo profissional)"}.get(occ["presos"], NI)
    pend = bloq + info
    itxt = image_text(ana, img)
    secoes = [
        ["Identificação da ocorrência", occ["id"]],
        ["Data e horário", occ["created_at"].replace("T", " ")],
        ["Profissional responsável", prof],
        ["Localização", loc],
        ["Tipo de ocorrência", fmt(occ["tipo"])],
        ["Informações dos veículos", veic],
        ["Quantidade de vítimas informada", f"{fmt(occ['n_vitimas'])} (declarada pelo profissional)"],
        ["Pessoas presas", presos],
        ["Riscos identificados", "\n".join("• " + r for r in reasons) or "Nenhum risco identificado nas informações disponíveis"],
        ["Resultado da análise da imagem", itxt],
        ["Classificação de prioridade operacional", f"{LABEL[pri]} — sugestão, sujeita à revisão humana"],
        ["Apoio solicitado", fmt(occ["apoio"])],
        ["Pendências de informação", "\n".join("• " + p for p in pend) or "Nenhuma pendência registrada"],
    ]
    return {"secoes": secoes, "id": occ["id"], "tipo": fmt(occ["tipo"]), "prof": prof, "loc": loc,
            "veic": fmt(occ["n_veiculos"]), "vit": fmt(occ["n_vitimas"]), "presos": presos, "descricao": fmt(occ["descricao"]),
            "imagem": itxt, "prioridade": LABEL[pri], "pri": pri, "motivos": reasons, "pendencias": pend}


def template_texts(f):
    pend = f"Pendências: {'; '.join(f['pendencias'])}." if f["pendencias"] else "Sem pendências de informação registradas."
    resumo = (f"Ocorrência {f['id']} ({f['tipo']}) registrada por {f['prof']} em {f['loc']}. "
              f"Informado pelo profissional: {f['veic']} veículo(s), {f['vit']} vítima(s), pessoas presas: {f['presos']}. "
              f"Análise de imagem: {f['imagem']} Prioridade operacional sugerida: {f['prioridade']} (sujeita à revisão humana). {pend}")
    base = {"ALTA": "Sugere-se encaminhar ao CCO com sinalização de prioridade alta para avaliação imediata da coordenação e da regulação médica",
            "MEDIA": "Sugere-se encaminhar ao CCO com prioridade média e acompanhamento da evolução do cenário",
            "VERIFICACAO": "Sugere-se verificação humana adicional antes do encaminhamento; informações ou confiança insuficientes",
            "SEM_INDICACAO": "Sem indicação operacional identificada nas informações disponíveis; encaminhar ao CCO para registro, se o profissional julgar pertinente"}[f["pri"]]
    return resumo, base + ". Este relatório não constitui diagnóstico clínico nem substitui a decisão do profissional ou a regulação médica."


def _parse(txt):
    txt = txt.strip().strip("`")
    txt = txt[4:] if txt.lower().startswith("json") else txt
    return json.loads(txt)


_OK_MODEL = {}


def _gemini_call(cfg, model, payload):
    r = requests.post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                      timeout=cfg["LLM_TIMEOUT"], headers={"x-goog-api-key": cfg["GEMINI_API_KEY"], "content-type": "application/json"},
                      json={"systemInstruction": {"parts": [{"text": SYSTEM}]}, "contents": [{"role": "user", "parts": [{"text": payload}]}],
                            "generationConfig": {"responseMimeType": "application/json", "maxOutputTokens": 8192}})
    r.raise_for_status()
    cand = r.json()["candidates"][0]
    txt = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
    try:
        return _parse(txt)
    except ValueError:
        raise ValueError(f"resposta do Gemini incompleta (finishReason={cand.get('finishReason')}); tente novamente")


def _gemini(cfg, payload):
    """Tenta o modelo configurado; se der 404/400, descobre modelos disponíveis para a chave (ListModels)."""
    key = cfg["GEMINI_API_KEY"]
    first = _OK_MODEL.get(key) or cfg["GEMINI_MODEL"]
    for tentativa in range(3):  # 503/429 = sobrecarga temporária: tenta de novo com espera
        try:
            return _gemini_call(cfg, first, payload)
        except requests.HTTPError as e:
            code = e.response.status_code if e.response is not None else 0
            if code in (503, 429, 500) and tentativa < 2:
                time.sleep(2 * (tentativa + 1))
                continue
            if code not in (400, 404, 429, 500, 503):
                raise
            break
        except (requests.Timeout, requests.ConnectionError):
            if tentativa < 1:
                time.sleep(2)
                continue
            raise RuntimeError("o Gemini demorou demais para responder (timeout); tente novamente em instantes")
    r = requests.get("https://generativelanguage.googleapis.com/v1beta/models?pageSize=200", headers={"x-goog-api-key": key}, timeout=cfg["LLM_TIMEOUT"])
    r.raise_for_status()
    names = [m["name"].split("/")[-1] for m in r.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    cand = [n for n in names if "flash" in n and n != first and not any(x in n for x in ("image", "tts", "live", "audio", "embed", "thinking", "robotics"))]
    cand.sort(key=lambda n: ("lite" in n, "preview" in n or "exp" in n, n))
    last = None
    for m in cand[:4]:
        try:
            out = _gemini_call(cfg, m, payload)
            _OK_MODEL[key] = m
            return out
        except Exception as ex:
            last = ex
    raise RuntimeError(f"nenhum modelo Gemini respondeu (disponíveis: {', '.join(names[:8]) or 'nenhum'}); último erro: {last}")


def llm_call(cfg, facts):
    """Gemini (gratuito, AI Studio) se GEMINI_API_KEY existir; senão Anthropic; senão falha => contingência."""
    payload = json.dumps({k: facts[k] for k in ("secoes", "descricao", "motivos", "pendencias", "prioridade")}, ensure_ascii=False)
    if cfg.get("GEMINI_API_KEY"):
        return _gemini(cfg, payload)
    if not cfg.get("LLM_API_KEY"):
        raise RuntimeError("API de IA não configurada")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=cfg["LLM_TIMEOUT"],
                      headers={"x-api-key": cfg["LLM_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": cfg["LLM_MODEL"], "max_tokens": 900, "system": SYSTEM, "messages": [{"role": "user", "content": payload}]})
    r.raise_for_status()
    return _parse(r.json()["content"][0]["text"])


def generate(cfg, facts, overrides=None):
    """Retorna conteúdo do relatório. Sem IA => contingência por template (identificada)."""
    resumo, enc = template_texts(facts)
    mode, note = "contingencia", ""
    if overrides:
        resumo, enc, mode = overrides["resumo"], overrides["encaminhamento"], "editado"
    else:
        try:
            out = (cfg.get("LLM_FN") or llm_call)(cfg, facts)
            r, e = str(out["resumo"]).strip(), str(out["encaminhamento"]).strip()
            if not r or not e:
                raise ValueError("resposta vazia")
            resumo, enc, mode = r, e, "ia"
        except Exception as ex:
            note = f"IA indisponível ({ex}); relatório gerado por template de contingência."
    label = {"ia": "IA (modelo de linguagem)", "contingencia": "Contingência por template (IA indisponível)",
             "editado": "Editado manualmente pelo profissional"}[mode]
    secoes = facts["secoes"] + [["Resumo operacional", resumo], ["Encaminhamento sugerido", enc]]
    return {"mode": mode, "note": note, "content": {"secoes": secoes, "resumo": resumo, "encaminhamento": enc,
            "pendencias": facts["pendencias"], "modo_label": label}}
