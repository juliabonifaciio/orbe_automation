"""Aprovação humana obrigatória (independente de qualquer acionamento)."""
import json
import db as D


class ApprovalError(Exception):
    pass


def current_report(oid):
    return D.one("select * from reports where occurrence_id=? and status!='substituido' order by version desc limit 1", (oid,))


def decide(oid, approver, decision, justification, now):
    rep, occ = current_report(oid), D.one("select * from occurrences where id=?", (oid,))
    if not rep or rep["status"] != "pendente":
        raise ApprovalError("Não há relatório pendente de decisão.")
    approver, justification = (approver or "").strip(), (justification or "").strip()
    if not approver:
        raise ApprovalError("Informe o responsável pela decisão.")
    if decision == "aprovar":
        bloq = [p for p in json.loads(rep["content"])["pendencias"] if p.startswith("Localização incompleta")]
        if bloq:
            raise ApprovalError("Complemente a localização antes de aprovar: " + "; ".join(bloq))
        if occ["priority"] == "VERIFICACAO" and not justification:
            raise ApprovalError("Prioridade 'Necessita de verificação': registre a justificativa da revisão humana.")
        st = "aprovado"
    elif decision == "rejeitar":
        if not justification:
            raise ApprovalError("Informe a justificativa da rejeição.")
        st = "rejeitado"
    else:
        raise ApprovalError("Decisão inválida.")
    D.ex("update reports set status=? where id=?", (st, rep["id"]))
    D.ex("update occurrences set status=? where id=?", (st, oid))
    D.ex("insert into approvals(report_id,occurrence_id,approver,decision,justification,created_at) values(?,?,?,?,?,?)",
         (rep["id"], oid, approver, decision, justification, now))
    return st
