# ARCHITECTURE.md — Arquitectura Swarm & Omnicanal Hermes Commercial
## Aliun Travel SRL · Septiembre 2026 · COS-v3.5 (TO-BE)

---

## Modelo Orquestador

**`google/gemini-2.0-flash-001`** (Vía OpenRouter)
- Contexto: **1M tokens**
- Function calling nativo, latencia ultra-baja (<1.5s)
- Orquestación de intención, despacho de sub-agentes, control de contexto conversacional y audio sessions.

---

## Sub-agentes Especializados

| Agente | Modelo OpenRouter | Contexto | Función |
|--------|-------------------|----------|---------|
| **vendedor** | `google/gemini-2.0-flash-lite-001` | 1M | Conversación de ventas, construcción de valor, negociación y diálogo en tiempo real de voz |
| **cotizador** | `qwen/qwen3.5-flash-02-23` | 1M | RPCs Supabase determinísticas, paridad de inventario y cálculo de precios |
| **qa-followup** | `mistralai/ministral-8b-2512` | 262K | Cadencia de seguimientos automáticos T+2h/24h/48h |
| **finanzas** | `qwen/qwen3.6-flash` | 1M | OCR y validación de comprobantes de pago + alerta directiva |
| **qa-auditor** | `google/gemini-2.0-flash-lite-001` | 1M | Auditoría continua de calidad comercial y afinación de prompts |

---

## Arquitectura Omnicanal (Dual-Channel + Voice Realtime)

El canal de entrada actúa estrictamente como un **Transport Adapter**. La sesión, contexto y estado residen de forma unificada en `conversation_sessions` y `crm_leads`.

```
Canal Entrada:
  ├─ WhatsApp (Meta Cloud API / Baileys Gateway)
  ├─ Chatwoot (Inbox Web / Escalación Humana)
  └─ ChatGPT Voice / Realtime Voice Gateway (Voz en Tiempo Real)
       │
       ▼
  Webhook Inbound (`canal_recibir_mensaje`)
       │
       ▼
  Hermes Commercial Orquestador (Gemini 2.0 Flash)
       ├─ Clasifica intención & perfila cliente
       ├─ Orquesta sub-agentes (vendedor, cotizador, finanzas)
       ├─ Consulta SSOT de Ariadne Data & Paridad Atlas Intel
       ├─ Valida tasa cambiaria oficial en Misión Control Live (`public.exchange_rates`)
       └─ Genera respuesta (`canal_enviar_respuesta` / Audio Stream / DOC-1 PDF)
```

---

## Voice Architecture: ChatGPT Voice / Realtime Gateway

1. **Protocolo:** Webhook bidireccional / WebSocket de audio streaming.
2. **Componentes del Pipeline de Voz:**
   - **Ingesta:** Captura de audio del cliente (llamada entrante / IVR inteligente).
   - **STT & Speech Engine:** ChatGPT Voice Provider API (OpenAI Realtime / ChatGPT Voice Endpoint).
   - **Context Injection:** Inyección de `session_id`, historial de cliente y `hotel_knowledge` en caliente.
   - **Tool Execution:** Invocación de `consultar_disponibilidad` y `calcular_cotizacion` durante la llamada.
   - **TTS & Retorno:** Generación de voz natural y respuesta fluida de audio al cliente.
3. **Estado de Integración:** Arquitectura y esquemas de base de datos (`conversation_sessions`, `voice_sessions`) listos; activable inmediatamente al inyectar la API key del proveedor en el entorno de despliegue.

---

## Infraestructura & Servidores

| Componente | URL / Host | Propósito |
|-----------|------------|-----------|
| MCP Server | `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp` | 18 tools comerciales, RPCs Supabase |
| n8n Workflows | `https://n8n-n8n.xaruuo.easypanel.host` | Orquestación de webhooks y disparadores |
| Chatwoot | `https://n8n-chatwoot.xaruuo.easypanel.host` | Inbox omnicanal y takeover humano |
| Voice Gateway | `hermes-gateway` (Puerto 8644 / Realtime Endpoint) | Puente de voz y streaming de audio |
| Supabase | `oyihiyivdhfxpyiwnmqk.supabase.co` | Base de datos relacional y vector store |

---

## Fallback de Modelos de Lenguaje

Si Gemini 2.0 Flash experimenta degradación:
1. `meta-llama/llama-4-maverick` (1M ctx)
2. `qwen/qwen3.6-flash` (1M ctx)
3. `deepseek/deepseek-v4-flash` (1M ctx)

---

*Hermes Commercial · Aliun Travel SRL · TO-BE COS-v3.5*
