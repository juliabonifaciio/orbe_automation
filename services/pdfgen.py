from xml.sax.saxutils import escape as E
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle


def build(path, occ, content, status_label, approvals, dispatches):
    st = getSampleStyleSheet()
    b = ParagraphStyle("b", parent=st["BodyText"], fontSize=9.5, leading=13)
    doc = SimpleDocTemplate(str(path), pagesize=A4, title=f"Relatório {occ['id']}", leftMargin=40, rightMargin=40, topMargin=40, bottomMargin=40)
    el = [Paragraph("ORBE — Relatório operacional de ocorrência", st["Title"]),
          Paragraph(f"Status: <b>{E(status_label)}</b> | Modo de geração: {E(content['modo_label'])}", b), Spacer(1, 8)]
    rows = [[Paragraph(f"<b>{E(t)}</b>", b), Paragraph(E(str(v)).replace("\n", "<br/>"), b)] for t, v in content["secoes"]]
    tb = Table(rows, colWidths=[140, 375])
    tb.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#9aa6d0")),
                            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef1ff"))]))
    el += [tb, Spacer(1, 10), Paragraph("<b>Decisões humanas</b>", b)]
    el += [Paragraph(E(f"{a['created_at']} — {a['decision']} por {a['approver']}. {a['justification'] or ''}"), b) for a in approvals] or [Paragraph("Nenhuma decisão registrada.", b)]
    el.append(Paragraph("<b>Encaminhamentos ao CCO (simulados)</b>", b))
    el += [Paragraph(E(f"{d['created_at']} — {d['status']}: {d['detail']}"), b) for d in dispatches] or [Paragraph("Nenhum encaminhamento registrado.", b)]
    el += [Spacer(1, 10), Paragraph("<i>Apoio operacional. Não constitui diagnóstico clínico nem substitui a avaliação do profissional ou a regulação médica.</i>", b)]
    doc.build(el)
