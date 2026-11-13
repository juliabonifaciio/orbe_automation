"""Encaminhamento ao CCO — SIMULAÇÃO (não há integração real com a Motiva)."""
import json
import uuid
import db as D
from .approval import current_report


class ApprovalRequired(Exception):
    pass


class DispatchError(Exception):
    pass


def simulated_transport(payload):
    return {"protocolo": "SIM-" + uuid.uuid4().hex[:8].upper(),
            "aviso": "ENVIO SIMULADO: nenhuma integração real com o CCO da Motiva foi acionada."}


def failing_transport(payload):
    raise DispatchError("Falha simulada de comunicação com o CCO (modo demonstração).")


def send(oid, transport, now):
    rep = current_report(oid)
    if not rep or rep["status"] != "aprovado":
        raise ApprovalRequired("Relatório não aprovado: encaminhamento ao CCO bloqueado.")
    payload = {"ocorrencia": oid, "versao": rep["version"], "relatorio": json.loads(rep["content"])}
    try:
        detail, status = json.dumps(transport(payload), ensure_ascii=False), "enviado_simulado"
    except Exception as e:
        detail, status = str(e), "falha"
    D.ex("insert into dispatches(occurrence_id,report_id,status,simulated,detail,created_at) values(?,?,?,?,?,?)",
         (oid, rep["id"], status, 1, detail, now))
    D.ex("update occurrences set status=? where id=?", ("encaminhado" if status == "enviado_simulado" else "encaminhamento_falhou", oid))
    return status, detail
