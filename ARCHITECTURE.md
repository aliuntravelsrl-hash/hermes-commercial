# ARCHITECTURE.md — Arquitectura Swarm Hermes Commercial
## Aliun Travel SRL · 29 MAY 2026

---

## Modelo Orquestador

**`google/gemini-2.0-flash-001`**
- Contexto: **1M tokens**
- Input: **$0.10 / 1M tokens**
- Output: **$0.40 / 1M tokens**
- Function calling nativo, velocidad <2s
- Cache read: $0.025/1M (75% descuento en prompts repetidos)

### Costo mensual estimado (200 conversaciones/día)
- Input: ~600K tokens/día = $0.06/día
- Output: ~200K tokens/día = $0.08/día
- **Mensual: ~$4-5 USD** (solo orquestador)

---

## Sub-agentes

| Agente | Modelo OpenRouter | Contexto | Input/1M | Output/1M | Función |
|--------|-------------------|----------|----------|-----------|---------|
| **vendedor** | `google/gemini-2.0-flash-lite-001` | 1M | $0.07 | $0.30 | Conversación ventas + construcción de valor |
| **cotizador** | `qwen/qwen3.5-flash-02-23` | 1M | $0.07 | $0.26 | RPCs Supabase + cálculos de precio |
| **qa-followup** | `mistralai/ministral-8b-2512` | 262K | $0.15 | $0.15 | Seguimientos T+2h/24h/48h |
| **finanzas** | `qwen/qwen3.6-flash` | 1M | $0.19 | $1.12 | Validación de pagos + depósitos |

### Costo sub-agentes mensual estimado
- vendedor: ~$3-5/mes
- cotizador: ~$2-3/mes
- qa-followup: ~$1-2/mes
- finanzas: ~$1-2/mes
- **Total sub-agentes: ~$7-12/mes**

### Costo total orquestación + sub-agentes: **~$11-17 USD/mes**

---

## Flujo de mensajes

```
Cliente WhatsApp (+1 809-510-9396)
  → Meta Cloud API
    → Webhook Meta → Chatwoot
      → Webhook Chatwoot message_created → n8n
        → Hermes Commercial (orquestador)
          ├─ Clasifica intención
          ├─ Despacha a sub-agente
          │   ├─ vendedor (E2-E4: conexión, descubrimiento, valor)
          │   ├─ cotizador (E5: disponibilidad, precio, paquete)
          │   ├─ finanzas (E8: comprobante, depósito)
          │   └─ qa-followup (E10: seguimientos)
          ├─ Ejecuta tools MCP/Supabase
          └─ Responde vía Chatwoot API → Meta Cloud API → Cliente
```

---

## Infraestructura

| Componente | URL | Propósito |
|-----------|-----|-----------|
| MCP Server | `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp` | 18 tools, 5/5 RPCs E2E OK |
| n8n | `https://n8n-n8n.xaruuo.easypanel.host` | Orquestación workflows |
| Chatwoot | `https://n8n-chatwoot.xaruuo.easypanel.host` | Inbox humano + escalamiento |
| Supabase (MCP) | `qxlmnsnxwlmfhspjehbh.supabase.co` | Base de datos producción |
| EasyPanel | `72.61.12.170:3000` | Deploy servicios |

---

## WhatsApp Canal Oficial

| Campo | Valor |
|-------|-------|
| Número | +1 809-510-9396 |
| Meta App ID | 4369066433358667 |
| WABA ID | 1664245875019293 |
| Phone Number ID | 1200844416435868 |
| System User | adminsrl (ID 61577055742856, token permanente) |
| Permisos | whatsapp_business_messaging + management + manage_events |

---

## Fallback

Si Gemini 2.0 Flash no disponible:
1. `meta-llama/llama-4-maverick` (1M ctx, $0.15/$0.60)
2. `qwen/qwen3.6-flash` (1M ctx, $0.19/$1.12)
3. `deepseek/deepseek-v4-flash` (1M ctx, $0.10/$0.20)

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
