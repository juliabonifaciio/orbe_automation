import sqlite3
from flask import g, current_app

SCHEMA = """
create table if not exists professionals(id integer primary key, name text unique not null, created_at text);
create table if not exists occurrences(
  id text primary key, professional_id integer references professionals(id),
  rodovia text, km text, sentido text, tipo text, n_veiculos integer, n_vitimas integer,
  presos text default 'nao_informado', descricao text, apoio text,
  status text default 'em_andamento', priority text, created_at text, closed_at text);
create table if not exists images(id integer primary key, occurrence_id text references occurrences(id),
  filename text, original_name text, width integer, height integer, sharpness real, brightness real, created_at text);
create table if not exists analyses(id integer primary key, occurrence_id text references occurrences(id),
  image_id integer, detector text, status text, detections text, note text, duration_ms integer, created_at text);
create table if not exists triage(id integer primary key, occurrence_id text references occurrences(id),
  priority text, reasons text, created_at text);
create table if not exists reports(id integer primary key, occurrence_id text references occurrences(id),
  version integer, mode text, mode_note text, content text, status text, created_at text);
create table if not exists approvals(id integer primary key, report_id integer references reports(id),
  occurrence_id text, approver text, decision text, justification text, created_at text);
create table if not exists change_log(id integer primary key, occurrence_id text, report_id integer,
  author text, field text, old text, new text, created_at text);
create table if not exists dispatches(id integer primary key, occurrence_id text, report_id integer,
  status text, simulated integer default 1, detail text, created_at text);
"""


def conn():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("pragma foreign_keys=on")
    return g.db


def q(sql, a=()):
    return [dict(r) for r in conn().execute(sql, a).fetchall()]


def one(sql, a=()):
    r = q(sql, a)
    return r[0] if r else None


def ex(sql, a=()):
    c = conn()
    cur = c.execute(sql, a)
    c.commit()
    return cur.lastrowid


def init_app(app):
    with sqlite3.connect(app.config["DATABASE"]) as c:
        c.executescript(SCHEMA)

    @app.teardown_appcontext
    def _close(_):
        d = g.pop("db", None)
        if d is not None:
            d.close()
