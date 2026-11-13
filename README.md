# ORBE — A inteligência que conecta a ocorrência (Sprint 2 · Motiva)

Assistente operacional de Atendimento Pré-Hospitalar (APH) rodoviário. Registra a ocorrência, analisa a imagem, sugere prioridade com motivos, gera um relatório (IA ou template), exige **aprovação humana** e só então faz o encaminhamento **simulado** ao CCO. Não diagnostica nem substitui a regulação médica.

## Funcionalidades
Atendimento com ID único · upload validado + OpenCV · detector YOLO substituível · triagem configurável · relatório de 15 seções · aprovação/edição/rejeição/nova análise com versões e log · envio simulado com retry · PDF · painel com dados reais do SQLite · histórico com filtros · API para agente.

## Estrutura
`app.py` rotas e pipeline · `config.py` · `db.py` · `services/` (detector, imaging, triage, reporter, approval, dispatch, pdfgen) · `templates/` · `static/` · `tests/` · `docs/` · `models/` (pesos) · `uploads/` · `reports/` · `data/`.

## Executar (Windows)
```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python app.py        (ou execute run.bat)
```
Abra http://127.0.0.1:5000. Testes: `pytest -q`.

## Configuração opcional
- **YOLO:** `pip install ultralytics` e coloque os pesos em `models/orbe.pt` (ou `YOLO_MODEL` no `.env`). Classes reconhecidas: car/truck/bus/motorcycle, person, fire/smoke, rollover/capotamento, collision. Sem pesos, a análise fica “indisponível”; **nenhuma detecção é simulada**.
- **IA de texto:** defina `GEMINI_API_KEY` (gratuita, AI Studio; modelo em `GEMINI_MODEL`) ou `ANTHROPIC_API_KEY` (e `LLM_MODEL`). Sem chave ou em falha, usa-se o template de contingência, sinalizado.

## API (disparo pelo agente)
`POST /api/ocorrencias` (JSON: profissional, rodovia, km, sentido, tipo, n_veiculos, n_vitimas, presos, apoio, descricao) cria e gera o relatório; `GET /api/ocorrencias/<id>`. A aprovação é sempre humana, pela interface.

## Limitações
Sem integração real com o CCO da Motiva (simulação); modelo YOLO não incluído; sem autenticação de usuários; estimativa de ganho é hipotética (docs/estimativa_ganho.md).