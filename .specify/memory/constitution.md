# ALIUN Travel SRL — Constitution

## I. Cash Flow Primero
Sin dinero no hay proyecto. Todo feature, fix o mejora se evalúa primero por impacto en ventas.
El puente Chatwoot→cotización no es arquitectura, es supervivencia.

## II. Repo LIMPIO por Función
Cada repositorio tiene UN propósito. NUNCA mezclar:
- `atlas-hermes-v2` = Hermes Ops (infra, sello, Telegram)
- `hermes-commercial` = Hermes Commercial (ventas, WhatsApp)
- `hermes-marketing` = Hermes Marketing (demanda, ads)
- `Ariadne-Data` = Analytics (2do sombrero de Ops)
- `atlas-api-toolbox` = SQL migrations + GTIs + CAPI
- `atlas-cableados` = Mapa cables del ecosistema
- `atlas-admin-v2` = Mission Control V3.0
- `atlas-sales-mcp` = MCP 18 tools

## III. NUNCA Exponer Tokens
Service role keys, PATs, API keys SOLO en .env y EasyPanel.
NUNCA en chat, commits, código, ni screenshots.

## IV. Auditar Antes de Ejecutar
Supabase: auditar con `information_schema` — NUNCA confiar en inventario Notion.
RPC params: prefijo `p_` obligatorio. PostgreSQL: `limit` = `p_limit`.
No asumir columnas — verificar primero.

## V. ESM en Atlas
`"type": "module"` — imports con `.js` extension.
3 bugs eliminados para siempre: template literals sin backticks, `||` faltantes, CommonJS→ESM.

## VI. Org Viva — Nombres Claros
Hermes Ops = el cerebro operativo (YO)
Hermes Commercial = el vendedor (Alex)
Hermes Marketing = el generador de demanda
Antigravity C3 = web/código/gaps técnicos
Director = Aldo Hilario (decisiones, pagos, cuentas)

MUERTOS: OpenClaw C1, Paperclip C2, AION UI C5 — no referenciar.

## VII. Escuchar→QA vs Sellado→Consolidar→Configurar→Sellar
NUNCA push GitHub sin fases previas.
NUNCA modificar callback URL global de Meta.
bash `UID` es variable readonly — usar `CWUID`.

## VIII. Supabase BD Madre→Hijas
Dato actualizado en tabla madre. Tablas hijas = INSERT ONLY.
Patrón inmutable para auditoría.

## Governance
Constitution supersedes all other practices.
Enmiendas requieren: documentación + aprobación Director + migration plan.
El Director dice "paso" → Hermes despacha tarea con contexto completo.

**Version**: 1.0.0 | **Ratified**: 2026-06-07 | **Last Amended**: 2026-06-07
