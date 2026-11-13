import json

import db as D
from conftest import FakeDetector, analyze, jpg_bytes, new_occ
from services import approval, dispatch
from services.triage import classify


def row(app, sql, a=()):
    with app.app_context():
        return D.one(sql, a)


# ---- ocorrências
def test_cria_ocorrencia_com_id_e_data(app, client):
    oid = new_occ(client)
    o = row(app, "select * from occurrences where id=?", (oid,))
    assert oid.startswith("ORB-") and o["created_at"] and o["status"] == "em_andamento"


def test_nao_inventa_dados_desconhecidos(app, client):
    oid = new_occ(client, rodovia="", km="", n_vitimas="")
    o = row(app, "select * from occurrences where id=?", (oid,))
    assert o["rodovia"] is None and o["n_vitimas"] is None


# ---- imagens
def test_upload_valido_e_detector_disponivel(make_app):
    app = make_app(DETECTOR=FakeDetector([{"label": "car", "conf": 0.9}]))
    c = app.test_client()
    oid = new_occ(c)
    analyze(c, oid, jpg_bytes())
    a = row(app, "select * from analyses where occurrence_id=?", (oid,))
    assert a["status"] == "ok" and json.loads(a["detections"])[0]["label"] == "car"
    assert row(app, "select count(*) n from images")["n"] == 1


def test_imagem_invalida_nao_interrompe_atendimento(app, client):
    oid = new_occ(client)
    r = analyze(client, oid, b"isto nao e imagem", "x.jpg")
    assert "corrompido" in r.get_data(as_text=True)
    assert row(app, "select count(*) n from reports")["n"] == 1  # relatório gerado mesmo assim
    assert "formato" in analyze(client, oid, b"abc", "x.gif").get_data(as_text=True)


def test_imagem_acima_do_limite(make_app):
    app = make_app(MAX_IMAGE_MB=0.00001)
    c = app.test_client()
    oid = new_occ(c)
    assert "excede" in analyze(c, oid, jpg_bytes()).get_data(as_text=True)


def test_detector_indisponivel_nao_simula_deteccao(app, client):
    app.config["DETECTOR"] = FakeDetector(ok=False)
    oid = new_occ(client, n_veiculos="1", n_vitimas="0")
    analyze(client, oid, jpg_bytes())
    a = row(app, "select * from analyses where occurrence_id=?", (oid,))
    assert a["status"] == "indisponivel" and json.loads(a["detections"]) == []
    assert row(app, "select priority from occurrences where id=?", (oid,))["priority"] == "VERIFICACAO"


# ---- triagem
T = {"low_conf": 0.45, "victims_high": 3, "vehicles_medium": 2, "vehicles_high": 5}
OCC = {"rodovia": "BR-116", "km": "1", "sentido": "Sul", "n_veiculos": 1, "n_vitimas": 0, "presos": "nao"}


def ana(*dets):
    return {"status": "ok", "detections": [{"label": l, "conf": c} for l, c in dets]}


def test_incendio_gera_prioridade_alta():
    assert classify(OCC, ana(("fire", 0.8)), True, T)[0] == "ALTA"


def test_capotamento_baixa_confianca_exige_verificacao():
    pri, reasons, *_ = classify(OCC, ana(("rollover", 0.2)), True, T)
    assert pri == "VERIFICACAO" and any("baixa confiança" in r for r in reasons)


def test_pessoas_na_imagem_nao_significam_vitimas():
    pri, reasons, *_ = classify(OCC, ana(("person", 0.9)), True, T)
    assert pri == "MEDIA" and any("não indica" in r for r in reasons)


def test_sem_indicacao_quando_dados_completos():
    assert classify(OCC, ana(), True, T)[0] == "SEM_INDICACAO"


def test_localizacao_incompleta_gera_pendencia():
    pri, _, bloq, _ = classify({**OCC, "km": None}, ana(), True, T)
    assert pri == "VERIFICACAO" and bloq


# ---- relatório
def test_relatorio_contingencia_quando_ia_falha(app, client):
    def falha(cfg, facts):
        raise ConnectionError("API fora do ar")
    app.config["LLM_FN"] = falha
    oid = new_occ(client)
    r = analyze(client, oid)
    rep = row(app, "select * from reports where occurrence_id=?", (oid,))
    assert rep["mode"] == "contingencia" and "API fora do ar" in rep["mode_note"]
    assert "contingência" in r.get_data(as_text=True).lower()


def test_relatorio_com_ia_e_campos_nao_informados(app, client):
    app.config["LLM_FN"] = lambda cfg, f: {"resumo": "Resumo IA", "encaminhamento": "Enc IA"}
    oid = new_occ(client, apoio="", n_vitimas="")
    analyze(client, oid)
    rep = row(app, "select * from reports where occurrence_id=?", (oid,))
    c = json.loads(rep["content"])
    assert rep["mode"] == "ia" and len(c["secoes"]) == 15
    assert dict(c["secoes"])["Apoio solicitado"] == "Não informado"


# ---- aprovação e encaminhamento
def aprovado(app, client, **kw):
    oid = new_occ(client, **kw)
    analyze(client, oid)
    client.post(f"/ocorrencia/{oid}/decisao", data={"approver": "Ana", "decisao": "aprovar", "justificativa": "ok"})
    return oid


def test_encaminhamento_bloqueado_sem_aprovacao(app, client):
    oid = new_occ(client)
    analyze(client, oid)
    r = client.post(f"/ocorrencia/{oid}/encaminhar", follow_redirects=True)
    assert "bloqueado" in r.get_data(as_text=True)
    assert row(app, "select count(*) n from dispatches")["n"] == 0
    with app.app_context():
        try:
            dispatch.send(oid, dispatch.simulated_transport, "x")
            assert False
        except dispatch.ApprovalRequired:
            pass


def test_aprovacao_registra_responsavel_e_versao(app, client):
    oid = aprovado(app, client)
    a = row(app, "select * from approvals where occurrence_id=?", (oid,))
    assert a["approver"] == "Ana" and a["decision"] == "aprovar"
    assert row(app, "select status from reports where occurrence_id=?", (oid,))["status"] == "aprovado"


def test_nao_aprova_com_localizacao_incompleta_e_exige_justificativa(app, client):
    oid = new_occ(client, km="")
    analyze(client, oid)
    r = client.post(f"/ocorrencia/{oid}/decisao", data={"approver": "Ana", "decisao": "aprovar", "justificativa": "x"}, follow_redirects=True)
    assert "Complemente a localização" in r.get_data(as_text=True)
    client.post(f"/ocorrencia/{oid}/editar", data={"km": "10", "rodovia": "BR-116", "sentido": "Sul", "author": "Ana"})
    assert row(app, "select count(*) n from change_log where occurrence_id=?", (oid,))["n"] == 1
    r = client.post(f"/ocorrencia/{oid}/decisao", data={"approver": "Ana", "decisao": "rejeitar"}, follow_redirects=True)
    assert "justificativa" in r.get_data(as_text=True)


def test_encaminhamento_aprovado_e_falha_com_nova_tentativa(app, client):
    oid = aprovado(app, client)
    app.config["TRANSPORT"] = dispatch.failing_transport
    client.post(f"/ocorrencia/{oid}/encaminhar")
    assert row(app, "select status from occurrences where id=?", (oid,))["status"] == "encaminhamento_falhou"
    app.config["TRANSPORT"] = None
    client.post(f"/ocorrencia/{oid}/encaminhar")
    assert row(app, "select status from occurrences where id=?", (oid,))["status"] == "encaminhado"
    assert row(app, "select count(*) n from dispatches")["n"] == 2


# ---- persistência, histórico e fluxo completo
def test_persistencia_entre_instancias(make_app):
    a1 = make_app()
    oid = new_occ(a1.test_client())
    a2 = make_app()  # mesmo banco (tmp_path)
    assert row(a2, "select id from occurrences where id=?", (oid,)) is not None


def test_fluxo_ponta_a_ponta_pdf_e_historico(make_app, tmp_path):
    app = make_app(DETECTOR=FakeDetector([{"label": "fire", "conf": 0.9}, {"label": "car", "conf": 0.8}]))
    c = app.test_client()
    oid = new_occ(c)
    analyze(c, oid, jpg_bytes())
    assert row(app, "select priority from occurrences where id=?", (oid,))["priority"] == "ALTA"
    assert c.post(f"/ocorrencia/{oid}/encerrar").status_code == 302  # ainda não encaminhado
    assert row(app, "select status from occurrences where id=?", (oid,))["status"] == "aguardando_aprovacao"
    c.post(f"/ocorrencia/{oid}/decisao", data={"approver": "Ana", "decisao": "aprovar"})
    c.post(f"/ocorrencia/{oid}/encaminhar")
    c.post(f"/ocorrencia/{oid}/encerrar")
    assert row(app, "select status from occurrences where id=?", (oid,))["status"] == "encerrada"
    assert list((tmp_path / "rep").glob("*.pdf"))
    h = c.get("/historico?prioridade=ALTA").get_data(as_text=True)
    assert oid in h and "enviado_simulado" in h
    d = c.get("/").get_data(as_text=True)
    assert "Encaminhamentos concluídos" in d


def test_api_cria_ocorrencia_para_agente(client):
    r = client.post("/api/ocorrencias", json={"profissional": "Agente", "rodovia": "SP-070", "km": "5", "sentido": "Leste"})
    assert r.status_code == 201 and r.get_json()["status"] == "aguardando_aprovacao"
    assert client.post("/api/ocorrencias", json={}).status_code == 400
