"""ORBE — assistente operacional de APH rodoviário (Sprint 2 Motiva). Execute: python app.py"""
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from flask import (Flask, abort, current_app, flash, jsonify, redirect, render_template, request,
                   send_file, send_from_directory, url_for)

import db as D
from config import Config
from services import approval, detector as det, dispatch, imaging, pdfgen, reporter, triage as tri

STATUS = {"em_andamento": "Em andamento", "aguardando_aprovacao": "Aguardando aprovação", "aprovado": "Aprovado — envio pendente",
          "rejeitado": "Relatório rejeitado", "encaminhado": "Encaminhado ao CCO (simulado)",
          "encaminhamento_falhou": "Envio falhou — pendente", "encerrada": "Encerrada"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def to_int(v):
    try:
        return int(str(v).strip()) if str(v).strip() != "" else None
    except (ValueError, TypeError):
        return None


def create_occurrence(f):
    name = (f.get("profissional") or "").strip()
    if not name:
        raise ValueError("Informe o profissional responsável.")
    p = D.one("select id from professionals where name=?", (name,)) or {"id": D.ex("insert into professionals(name,created_at) values(?,?)", (name, now()))}
    oid = f"ORB-{datetime.now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}"
    presos = f.get("presos") if f.get("presos") in ("sim", "nao") else "nao_informado"
    g = lambda k: (f.get(k) or "").strip() or None
    D.ex("insert into occurrences(id,professional_id,rodovia,km,sentido,tipo,n_veiculos,n_vitimas,presos,descricao,apoio,status,created_at)"
         " values(?,?,?,?,?,?,?,?,?,?,?,?,?)",
         (oid, p["id"], g("rodovia"), g("km"), g("sentido"), g("tipo"), to_int(f.get("n_veiculos")), to_int(f.get("n_vitimas")),
          presos, g("descricao"), g("apoio"), "em_andamento", now()))
    return oid


def last_analysis(oid):
    a = D.one("select * from analyses where occurrence_id=? order by id desc limit 1", (oid,))
    if a:
        a["detections"] = json.loads(a["detections"] or "[]")
    return a


def save_image(oid, file):
    cfg = current_app.config
    data = file.read()
    meta = imaging.validate(data, file.filename, cfg)
    fn = f"{oid}_{uuid.uuid4().hex[:8]}.{meta['ext']}"
    (Path(cfg["UPLOAD_DIR"]) / fn).write_bytes(data)
    iid = D.ex("insert into images(occurrence_id,filename,original_name,width,height,sharpness,brightness,created_at) values(?,?,?,?,?,?,?,?)",
               (oid, fn, file.filename, meta["width"], meta["height"], meta["sharpness"], meta["brightness"], now()))
    return D.one("select * from images where id=?", (iid,))


def analyze(oid, img):
    cfg = current_app.config
    d = cfg.get("DETECTOR") or det.get_detector(cfg)
    t0, dets, status, note = time.time(), [], "ok", ""
    if not d.available():
        status, note = "indisponivel", d.reason
    else:
        try:
            dets = d.detect(Path(cfg["UPLOAD_DIR"]) / img["filename"])
        except Exception as e:
            status, note = "erro", f"falha no detector: {e}"
    D.ex("insert into analyses(occurrence_id,image_id,detector,status,detections,note,duration_ms,created_at) values(?,?,?,?,?,?,?,?)",
         (oid, img["id"], d.name, status, json.dumps(dets), note, int((time.time() - t0) * 1000), now()))
    return last_analysis(oid)


def make_report(oid, overrides=None):
    """Triagem + relatório (nova versão). Dados nunca se perdem se a IA falhar."""
    cfg = current_app.config
    occ = D.one("select * from occurrences where id=?", (oid,))
    prof = D.one("select name from professionals where id=?", (occ["professional_id"],))["name"]
    img = D.one("select * from images where occurrence_id=? order by id desc limit 1", (oid,))
    ana = last_analysis(oid)
    pri, reasons, bloq, info = tri.classify(occ, ana, bool(img), cfg["TRIAGE"])
    D.ex("insert into triage(occurrence_id,priority,reasons,created_at) values(?,?,?,?)", (oid, pri, json.dumps(reasons, ensure_ascii=False), now()))
    D.ex("update occurrences set priority=? where id=?", (pri, oid))
    occ["priority"] = pri
    res = reporter.generate(cfg, reporter.build_facts(occ, prof, ana, img, pri, reasons, bloq, info), overrides)
    v = (D.one("select max(version) m from reports where occurrence_id=?", (oid,))["m"] or 0) + 1
    D.ex("update reports set status='substituido' where occurrence_id=? and status in ('pendente','aprovado','rejeitado')", (oid,))
    rid = D.ex("insert into reports(occurrence_id,version,mode,mode_note,content,status,created_at) values(?,?,?,?,?,?,?)",
               (oid, v, res["mode"], res["note"], json.dumps(res["content"], ensure_ascii=False), "pendente", now()))
    D.ex("update occurrences set status='aguardando_aprovacao' where id=?", (oid,))
    return rid, res


def run_pipeline(oid, file=None, reanalyze=False):
    img = None
    if file is not None and file.filename:
        try:
            img = save_image(oid, file)
            analyze(oid, img)
        except imaging.ImageError as e:  # Regra 6: erro informado, atendimento continua
            flash(f"Imagem não aceita: {e}. O atendimento continua sem essa imagem.", "erro")
    elif reanalyze:
        img = D.one("select * from images where occurrence_id=? order by id desc limit 1", (oid,))
        if img:
            analyze(oid, img)
    rid, res = make_report(oid)
    if res["note"]:
        flash(res["note"], "aviso")  # Regra 5
    return rid


def stats():
    n = lambda sql, a=(): D.one(sql, a)["n"]
    openq = "status not in ('encaminhado','encerrada')"
    avg = D.one("select avg((julianday(a.created_at)-julianday(o.created_at))*1440) m from approvals a join occurrences o on o.id=a.occurrence_id where a.decision='aprovar'")["m"]
    return {"total": n("select count(*) n from occurrences"), "andamento": n(f"select count(*) n from occurrences where {openq}"),
            "revisao": n(f"select count(*) n from occurrences where {openq} and priority='VERIFICACAO'"),
            "rel_pend": n("select count(*) n from reports where status='pendente'"), "rel_apr": n("select count(*) n from reports where status='aprovado'"),
            "env_pend": n("select count(*) n from occurrences where status in ('aprovado','encaminhamento_falhou')"),
            "env_ok": n("select count(*) n from occurrences where status in ('encaminhado','encerrada')"),
            "prio": {r["priority"]: r["n"] for r in D.q("select priority, count(*) n from occurrences where priority is not null group by priority")},
            "tempo": None if avg is None else round(avg, 1)}


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    for k in ("UPLOAD_DIR", "REPORT_DIR"):
        Path(app.config[k]).mkdir(parents=True, exist_ok=True)
    Path(app.config["DATABASE"]).parent.mkdir(parents=True, exist_ok=True)
    D.init_app(app)

    @app.context_processor
    def ctx():
        return {"STATUS": STATUS, "PLABEL": tri.LABEL}

    @app.template_filter("dt")
    def _dt(s):
        return datetime.fromisoformat(s).strftime("%d/%m/%Y %H:%M") if s else "—"

    @app.errorhandler(413)
    def too_big(_):
        flash("Arquivo excede o limite de envio. O atendimento continua.", "erro")
        return redirect(request.referrer or url_for("dashboard"))

    @app.errorhandler(404)
    def nf(_):
        return render_template("error.html", msg="Página ou ocorrência não encontrada."), 404

    @app.get("/")
    def dashboard():
        recent = D.q("select o.*, p.name prof from occurrences o join professionals p on p.id=o.professional_id order by o.created_at desc limit 6")
        return render_template("dashboard.html", s=stats(), recent=recent)

    @app.route("/novo", methods=["GET", "POST"])
    def novo():
        if request.method == "POST":
            try:
                return redirect(url_for("ocorrencia", oid=create_occurrence(request.form)))
            except ValueError as e:
                flash(str(e), "erro")
        return render_template("novo.html", f=request.form)

    def load(oid):
        o = D.one("select o.*, p.name prof from occurrences o join professionals p on p.id=o.professional_id where o.id=?", (oid,))
        return o or abort(404)

    @app.get("/ocorrencia/<oid>")
    def ocorrencia(oid):
        o = load(oid)
        rep = approval.current_report(oid)
        content = json.loads(rep["content"]) if rep else None
        ana, img = last_analysis(oid), D.one("select * from images where occurrence_id=? order by id desc limit 1", (oid,))
        tr = D.one("select * from triage where occurrence_id=? order by id desc limit 1", (oid,))
        st = o["status"]
        done = [True, bool(ana), bool(tr), bool(rep), st in ("aprovado", "encaminhado", "encaminhamento_falhou", "encerrada"),
                st in ("encaminhado", "encerrada"), st == "encerrada"]
        blocked = bool(content and any(p.startswith("Localização incompleta") for p in content["pendencias"]))
        return render_template("ocorrencia.html", o=o, rep=rep, c=content, ana=ana, img=img, reasons=json.loads(tr["reasons"]) if tr else [],
                               done=done, blocked=blocked, versions=D.q("select version,mode,status,created_at from reports where occurrence_id=? order by version desc", (oid,)),
                               aprs=D.q("select * from approvals where occurrence_id=? order by id desc", (oid,)),
                               disps=D.q("select * from dispatches where occurrence_id=? order by id desc", (oid,)),
                               chg=D.q("select * from change_log where occurrence_id=? order by id desc", (oid,)))

    @app.post("/ocorrencia/<oid>/analisar")
    def analisar(oid):
        load(oid)
        run_pipeline(oid, request.files.get("imagem"), reanalyze=bool(request.form.get("reanalisar")))
        return redirect(url_for("ocorrencia", oid=oid))

    @app.post("/ocorrencia/<oid>/decisao")
    def decisao(oid):
        load(oid)
        try:
            approval.decide(oid, request.form.get("approver"), request.form.get("decisao"), request.form.get("justificativa"), now())
            flash("Decisão registrada.", "ok")
        except approval.ApprovalError as e:
            flash(str(e), "erro")
        return redirect(url_for("ocorrencia", oid=oid))

    @app.post("/ocorrencia/<oid>/editar")
    def editar(oid):
        o, f = load(oid), request.form
        if o["status"] in ("encaminhado", "encerrada"):
            flash("Ocorrência já encaminhada: edição bloqueada.", "erro")
            return redirect(url_for("ocorrencia", oid=oid))
        author = (f.get("author") or "").strip() or o["prof"]
        new = {"rodovia": (f.get("rodovia") or "").strip() or None, "km": (f.get("km") or "").strip() or None,
               "sentido": (f.get("sentido") or "").strip() or None, "n_veiculos": to_int(f.get("n_veiculos")),
               "n_vitimas": to_int(f.get("n_vitimas")), "descricao": (f.get("descricao") or "").strip() or None}
        cur = json.loads(approval.current_report(oid)["content"]) if approval.current_report(oid) else {}
        for k, v in new.items():
            if k in f and v != o[k]:
                D.ex("update occurrences set %s=? where id=?" % k, (v, oid))
                D.ex("insert into change_log(occurrence_id,author,field,old,new,created_at) values(?,?,?,?,?,?)", (oid, author, k, str(o[k]), str(v), now()))
        r, e = (f.get("resumo") or "").strip(), (f.get("encaminhamento") or "").strip()
        ov = {"resumo": r, "encaminhamento": e} if r and e and (r != cur.get("resumo") or e != cur.get("encaminhamento")) else None
        rid, _ = make_report(oid, ov)
        if ov:
            D.ex("insert into change_log(occurrence_id,report_id,author,field,old,new,created_at) values(?,?,?,?,?,?,?)", (oid, rid, author, "texto do relatório", cur.get("resumo", ""), r, now()))
        flash("Alterações registradas. Nova versão do relatório aguarda aprovação.", "ok")
        return redirect(url_for("ocorrencia", oid=oid))

    @app.post("/ocorrencia/<oid>/encaminhar")
    def encaminhar(oid):
        load(oid)
        transport = current_app.config.get("TRANSPORT") or (dispatch.failing_transport if request.form.get("falha_demo") else dispatch.simulated_transport)
        try:
            status, detail = dispatch.send(oid, transport, now())
            flash("Envio SIMULADO concluído. " + detail if status == "enviado_simulado" else "Falha no envio: ocorrência segue pendente; tente novamente. " + detail,
                  "ok" if status == "enviado_simulado" else "erro")
        except dispatch.ApprovalRequired as e:
            flash(str(e), "erro")  # Regra 4
        return redirect(url_for("ocorrencia", oid=oid))

    @app.post("/ocorrencia/<oid>/encerrar")
    def encerrar(oid):
        o = load(oid)
        if o["status"] not in ("encaminhado", "encerrada"):
            flash("Só é possível encerrar após o encaminhamento ao CCO.", "erro")
            return redirect(url_for("ocorrencia", oid=oid))
        D.ex("update occurrences set status='encerrada', closed_at=? where id=?", (now(), oid))
        _pdf(oid, "Encerrada")
        flash("Atendimento encerrado e PDF gerado.", "ok")
        return redirect(url_for("ocorrencia", oid=oid))

    def _pdf(oid, label):
        rep = approval.current_report(oid)
        if not rep:
            abort(404)
        path = Path(current_app.config["REPORT_DIR"]) / f"{oid}_v{rep['version']}.pdf"
        pdfgen.build(path, load(oid), json.loads(rep["content"]), label, D.q("select * from approvals where occurrence_id=?", (oid,)),
                     D.q("select * from dispatches where occurrence_id=?", (oid,)))
        return path

    @app.get("/ocorrencia/<oid>/pdf")
    def pdf(oid):
        o = load(oid)
        label = STATUS[o["status"]] if o["status"] in ("encaminhado", "encerrada", "aprovado") else "RASCUNHO — NÃO APROVADO"
        return send_file(_pdf(oid, label), mimetype="application/pdf")

    @app.get("/uploads/<fn>")
    def uploads(fn):
        return send_from_directory(current_app.config["UPLOAD_DIR"], fn)

    @app.get("/historico")
    def historico():
        q, p, s = request.args.get("q", "").strip(), request.args.get("prioridade", ""), request.args.get("status", "")
        sql, a = "select o.*, p.name prof from occurrences o join professionals p on p.id=o.professional_id where 1=1", []
        if q:
            sql += " and (o.id like ? or o.rodovia like ? or p.name like ?)"
            a += [f"%{q}%"] * 3
        if p:
            sql, a = sql + " and o.priority=?", a + [p]
        if s:
            sql, a = sql + " and o.status=?", a + [s]
        rows = D.q(sql + " order by o.created_at desc", a)
        for r in rows:
            r["disp"] = D.q("select status, created_at from dispatches where occurrence_id=? order by id desc", (r["id"],))
        return render_template("historico.html", rows=rows, q=q, p=p, s=s)

    # --- API para disparo pelo agente (aprovação humana continua exclusiva da interface) ---
    @app.post("/api/ocorrencias")
    def api_create():
        try:
            oid = create_occurrence(request.get_json(silent=True) or {})
        except ValueError as e:
            return jsonify(erro=str(e)), 400
        rid, res = make_report(oid)
        o = D.one("select status, priority from occurrences where id=?", (oid,))
        return jsonify(id=oid, relatorio_id=rid, modo=res["mode"], prioridade=o["priority"], status=o["status"], url=url_for("ocorrencia", oid=oid)), 201

    @app.get("/api/ocorrencias/<oid>")
    def api_get(oid):
        o = load(oid)
        rep = approval.current_report(oid)
        return jsonify(ocorrencia=o, relatorio=json.loads(rep["content"]) if rep else None, relatorio_status=rep["status"] if rep else None)

    return app


if __name__ == "__main__":
    create_app().run(debug=False, port=5000)
