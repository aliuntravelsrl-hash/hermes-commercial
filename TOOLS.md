# TOOLS.md — Hermes Commercial · Herramientas

**Repo oficial:** `aliuntravelsrl-hash/hermes-commercial`
**Orquestador:** Hermes Commercial (Gemini 2.0 Flash, 1M ctx)
**MCP Server:** `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp`
**Fecha:** 29 MAY 2026

---

## Principio rector

Un solo orquestador decide qué herramienta usar según el momento de la conversación.
Despacha a sub-agentes económicos para tareas específicas.

---

## Capa 1 — Tools nativas Supabase (motor comercial)

Se usan cuando el cliente está en fase de exploración, descubrimiento, comparación, validación, pricing o cotización.

| # | Tool | Propósito | Tablas Supabase | Estado |
|---|------|-----------|----------------|--------|
| 1 | `buscar_hoteles` | Busca hoteles por destino/nombre | `hotels_master` | ✅ Activa |
| 2 | `consultar_disponibilidad` | Precios y disponibilidad real por hotel/fechas/ocupación | `hotels_master` + `rates` | ✅ Activa |
| 3 | `calcular_cotizacion` | Arma cotización formal basada en parámetros reales | `hotels_master` + `rates` | ✅ Activa |
| 4 | `calcular_precio_paquete` | Convierte y proyecta precio total, incluido DOP | `rates` + `exchange_rates` | ✅ Activa |
| 5 | `validar_ocupacion_habitacion` | Verifica si la ocupación por habitación es válida | `rooms` (capacity_adults / capacity_children) | ✅ Activa |
| 6 | `buscar_ofertas_marketing` | Revisa promociones activas o flash sales | `marketing_offers` | ✅ Activa |

**Endpoint MCP:** `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp`
**Parámetros RPC:** Todos usan `p_` prefix (auditoría real Supabase). `p_limit` para reserved word.

---

## Capa 2 — Tools MCP (motor de cierre y post-cotización)

Se usan cuando el cliente avanza hacia cierre o gestión documental.

| # | Tool | Propósito | Tablas Supabase | Estado |
|---|------|-----------|----------------|--------|
| 1 | `generar_cotizacion_pdf` | Genera y entrega PDF formal | Lee `hotels_master` + rates → WF-GOTENBERG | 🔧 Pendiente WF |
| 2 | `validar_comprobante` | Revisa evidencia de pago enviada por el cliente | Lee `atlas_payments` → WF-DEPOSITO | 🔧 Pendiente WF |
| 3 | `registrar_deposito` | Registra abono con aprobación humana | Escribe `bookings` + `atlas_payments` | 🔧 Pendiente WF |
| 4 | `obtener_galeria_hotel` | Entrega fotos del hotel para soporte comercial | Lee `hotels_master` (gallery) | ✅ Activa |
| 5 | `registrar_lead` | Crea un nuevo lead de ventas en el CRM | Escribe `crm_leads` | ✅ Activa |
| 6 | `avanzar_pipeline` | Cambia el stage de un lead en el embudo | Escribe `crm_leads` + `crm_activities` | ✅ Activa |
| 7 | `registrar_actividad` | Agrega notas o logs al historial del lead | Escribe `crm_activities` | ✅ Activa |
| 8 | `crear_deal` | Convierte cotización en negociación formal | Escribe `crm_deals` | ✅ Activa |
| 9 | `consultar_pipeline` | Obtiene agregaciones del embudo | Lee `crm_leads` + `crm_deals` | ✅ Activa |

---

## Capa 3 — Tools de Memoria Postgres (motor de contexto)

Se usan para que el orquestador y sub-agentes tengan contexto de conversaciones previas y perfil del cliente.

| # | Tool | Propósito | Tablas Supabase | Estado |
|---|------|-----------|----------------|--------|
| 1 | `get_conversation_context` | Devuelve perfil + últimos mensajes + lead activo para un teléfono | `client_profiles` + `conversation_messages` + `crm_leads` | 🔧 Nueva |
| 2 | `save_message` | Guarda cada mensaje in/out de la conversación | `conversation_messages` (INSERT ONLY) | 🔧 Nueva |
| 3 | `upsert_client_profile` | Crea o actualiza perfil del cliente | `client_profiles` | 🔧 Nueva |

**Ver MEMORY.md** para SQL DDL completo y diseño de las RPCs.

---

## Columnas auditadas Supabase (production real)

```
rates:          adult_rate, valid_from, valid_to, is_active, child_rate, sgl_rate, dbl_rate, tpl_rate
                (NO base_price_usd)
rooms:          capacity_adults, capacity_children, capacity, room_type
                (NO max_adults, max_children, max_occupancy como integer)
marketing_offers: discount_percentage, is_published, valid_from, valid_until, allows_deposit, hotel_slug
                  (NO discount_percent, published, check_in_start)
exchange_rates:  currency_pair, rate_buy, rate_sell, is_active
                  (NO from_currency, to_currency, rate, effective_date)
```

**Doctrina:** NUNCA asumir nombres de columnas. Siempre auditar con `information_schema.columns`.

---

## Variables de entorno requeridas

| Variable | Uso | Donde vive |
|----------|-----|------------|
| `SUPABASE_URL` | Acceso a DB | EasyPanel env |
| `SUPABASE_SERVICE_ROLE_KEY` | Acceso service role | EasyPanel env |
| `OPENROUTER_API_KEY` | Routing a modelos | EasyPanel env |
| `CHATWOOT_URL` | Endpoint Chatwoot | EasyPanel env |
| `CHATWOOT_ACCOUNT_ID` | Cuenta Chatwoot | EasyPanel env |

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*


---

## HOTEL KNOWLEDGE TOOLS (HK-003 — 22 Jul 2026)

### Cuándo usar
Antes de responder cualquier pregunta específica sobre un hotel
(restaurantes, servicios, actividades, piscinas, políticas, secretos).
NO usar para precios ni disponibilidad — esos van a buscar_hoteles.

---

### `consultar_hotel_knowledge`
**RPC:** `consultar_y_registrar(hotel_id, pregunta, session_id?, lead_id?, agente, canal)`
**Endpoint:** `POST /rest/v1/rpc/consultar_y_registrar`

**Cuándo:** Cliente hace pregunta específica sobre el hotel.

**Payload:**
```json
{
  "p_hotel_id":   "uuid del hotel",
  "p_pregunta":   "¿tienen shows nocturnos?",
  "p_session_id": "uuid de la sesión activa",
  "p_lead_id":    "uuid del lead",
  "p_agente":     "hermes-commercial",
  "p_canal":      "whatsapp"
}
```

**Response:**
```json
{
  "encontrado": true,
  "hotel": "Hard Rock Hotel Punta Cana",
  "respuesta_sugerida": "El Hard Rock tiene shows nocturnos en el teatro Rock Star...",
  "confianza": 92,
  "gap_registrado": false
}
```

**Si gap_registrado=true:**
→ Usar `respuesta_sugerida` (respuesta genérica de espera)
→ NO inventar información
→ El gap queda en hotel_qa_log para que QA lo procese

---

### `registrar_gap_manual`
**RPC:** `registrar_knowledge_gap(hotel_id, pregunta_cliente, respuesta_dada, session_id?, lead_id?)`

**Cuándo:** El sub-agente detecta que su respuesta fue incompleta o incierta
DESPUÉS de haberla dado. Registra el gap para mejora futura.

---

### Flujo de decisión del sub-agente

```
¿Pregunta específica sobre el hotel?
    ↓ SÍ
consultar_hotel_knowledge()
    ↓
¿encontrado=true AND confianza>=80?
    SÍ → usar respuesta_sugerida directamente
    NO → usar respuesta_sugerida genérica
         gap_registrado=true automáticamente
         NO INVENTAR
```

---

### Regla absoluta
El sub-agente NUNCA escribe en hotel_knowledge.
Solo consulta y registra gaps.
La inteligencia del sistema crece via: gap → QA → Intel → Director → conocimiento canónico.
