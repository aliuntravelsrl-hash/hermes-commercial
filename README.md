# Hermes Commercial

## Propósito

Frente comercial oficial de ALIUN TRAVEL SRL. Agente orquestador swarm que convierte leads WhatsApp en reservas confirmadas.

## Identidad

**Hermes Commercial** — agente orquestador con modelo económico de amplio contexto.
Herencia limpia de Paperclip OTA + OpenClaw V2. Sin marketing. Solo SOP E2E del flujo del cliente.

## Cantera heredada

- `paperclip-ota-agents` — ARCHIVADO, solo lectura, fuente histórica
- `atlas-sales-v2` — ARCHIVADO, solo lectura, cantera inmediata

No se borran, no se modifican. Sirven como referencia.

## Estructura

```
hermes-commercial/
├── README.md                    # Este documento
├── SOUL.md                      # Alma del Gerente Comercial
├── IDENTITY.md                  # Identidad doctrinal Hermes Commercial
├── FRAMEWORK.md                 # 7 leyes de cierre (Kennedy+Belfort §16)
├── ROUTING.md                   # Matriz de ruteo comercial (6 departamentos)
├── RUTINA.md                    # 10 estados del flujo de venta E1→E10
├── TOOLS.md                     # 18 MCP tools + nativas
├── REHIDRATACION.md             # Rutina de arranque del orquestador
├── ARCHITECTURE.md              # Arquitectura swarm + modelos + costos
├── config/
│   └── routing_matrix.js        # Matriz de ruteo ejecutable
├── agents/
│   ├── vendedor.md              # Prompt sub-agente ventas
│   ├── cotizador.md             # Prompt sub-agente cotización
│   ├── qa-followup.md           # Prompt sub-agente seguimiento
│   └── finanzas.md              # Prompt sub-agente pagos
└── knowledge/
    └── extracted-intel.md       # Inteligencia heredada adaptada
```

## Flujo operativo

```
WhatsApp (+1 809-510-9396) → Meta Cloud API → Webhook → n8n
  → Hermes Commercial (orquestador swarm)
    → Sub-agente vendedor (conecta + cotiza)
    → Sub-agente cotizador (RPCs Supabase)
    → Sub-agente finanzas (valida pagos)
    → Sub-agente QA followup (T+2h/24h/48h)
    → Supabase (hotels, rates, bookings, crm_leads)
    → Chatwoot (inbox humano para escalamiento)
```

## Modelo orquestador

`google/gemini-2.0-flash-001` — 1M contexto, $0.10/$0.40 por 1M tokens

## MCP Server

`https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp` — `atlas-sales-tools v1.3.1`, 18 tools verificadas en vivo (08 JUN 2026). Firmas reales (sin prefijo `p_`) en `TOOLS_SCHEMA.md`. Pendiente: 3 RPCs de memoria (ver `MEMORY.md`).

## Fuente de verdad

- **Repo:** éste (`aliuntravelsrl-hash/hermes-commercial`)
- **MCP:** `aliuntravelsrl-hash/atlas-sales-mcp`
- **Notion War Room:** `35f293f4-6b24-8121-ac1d-f43b90ea8d37`

## Regla

No mezclar canteras en este repo. Solo estructura limpia con inteligencia heredada adaptada.

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
