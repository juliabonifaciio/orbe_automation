# Fluxo operacional — ORBE (Sprint 2)

## Problema
No atendimento pré-hospitalar rodoviário, informações da ocorrência (local, veículos, vítimas, riscos) são coletadas por rádio/telefone e registradas à mão, gerando atraso, dados incompletos e relatórios inconsistentes.

## Processo manual automatizado
Coletar dados → organizar → avaliar riscos olhando fotos → redigir relatório → revisar → comunicar ao CCO.

## Fluxo automatizado
```mermaid
flowchart TD
  A[Iniciar atendimento<br/>ID + data/hora] --> B[Enviar imagem?]
  B -- sim --> C{Imagem válida?}
  C -- não --> C1[Exceção Regra 6: erro informado,<br/>atendimento continua] --> E
  C -- sim --> D[Detector YOLO]
  D -- indisponível --> D1[Análise marcada como indisponível<br/>nada é simulado] --> E
  D --> E[Triagem por regras configuráveis]
  B -- não --> E
  E --> F{Prioridade sugerida}
  F -->|Alta / Média / Verificação / Sem indicação| G[Gerar relatório]
  G --> H{IA disponível?}
  H -- sim --> I[Relatório por IA]
  H -- não --> J[Contingência por template<br/>Regra 5]
  I --> K[Revisão humana]
  J --> K
  K -->|Editar / Nova análise| G
  K -->|Rejeitar + justificativa| G
  K -->|Aprovar| L{Localização completa?<br/>Regra 2}
  L -- não --> K
  L -- sim --> M[Encaminhar ao CCO - SIMULADO]
  M -- falha --> N[Pendente + nova tentativa<br/>Regra 7] --> M
  M -- ok --> O[Encerrar: PDF + histórico]
```

## Etapas de uso
1. **Iniciar**: formulário (campos vazios viram “Não informado”).
2. **Análise**: upload validado (formato, tamanho, decodificação) e detecção.
3. **Triagem**: prioridade com motivos explícitos.
4. **Relatório**: 15 seções; IA redige resumo/encaminhamento, ou template.
5. **Aprovação humana**: aprovar, editar, nova análise ou rejeitar.
6. **CCO (simulado)**: só com relatório aprovado.
7. **Encerramento**: PDF, status e histórico.

## Pontos de decisão e regras
| Regra | Descrição |
|---|---|
| 1 | Indício de incêndio/capotamento (confiança ≥ 0,45) → prioridade **Alta**, sujeita à revisão |
| 2 | Localização incompleta → pendência; aprovação bloqueada até complementar |
| 3 | Baixa confiança → “Necessita de verificação”; aprovação exige justificativa |
| 4 | Sem aprovação → encaminhamento bloqueado |
| 5 | IA indisponível → template de contingência identificado, sem perda de dados |
| 6 | Imagem inválida → erro informado, atendimento segue |
| 7 | Falha no envio → ocorrência pendente, nova tentativa |

Limiares ficam em `config.py` (`TRIAGE`). Pessoas na imagem não implicam vítimas; o sistema não diagnostica.

## Aprovação humana e CCO
A decisão (responsável, data/hora, versão, justificativa) é gravada em `approvals`; alterações em `change_log`. A API (`/api/ocorrencias`) permite ao agente criar a ocorrência e gerar o relatório, mas **não** aprovar nem encaminhar. O envio ao CCO é uma simulação funcional, identificada na interface e no PDF.
