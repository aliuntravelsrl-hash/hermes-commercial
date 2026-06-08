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

**Endpoint MCP:** `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp` (servidor `atlas-sales-tools v1.3.1`, 18 tools verificadas en vivo 08 JUN 2026)

> ⚠️ **Prefijo `p_`:** el `p_` aplica SOLO a los argumentos de la función RPC interna de Supabase. La **interfaz MCP que el agente invoca NO usa `p_`** (ej. `slug`, `hotel_id`, `check_in`). Llamar tools MCP con `p_hotel_slug` falla con `-32602`. Firmas reales verificadas en **`TOOLS_SCHEMA.md`**.

---

## Capa 2 — Tools MCP (motor de cierre y post-cotización)

Se usan cuando el cliente avanza hacia cierre o gestión documental.

| # | Tool | Propósito | Tablas Supabase | Estado |
|---|------|-----------|----------------|--------|
| 1 | `generar_cotizacion_pdf` | Genera y entrega PDF formal | Lee `hotels_master` + rates → WF-GOTENBERG | ✅ Activa (MCP v1.3.1) |
| 2 | `validar_comprobante` | Revisa evidencia de pago enviada por el cliente | Lee `atlas_payments` → WF-DEPOSITO | ✅ Activa (MCP v1.3.1) |
| 3 | `registrar_deposito` | Registra abono con aprobación humana | Escribe `bookings` + `atlas_payments` | ✅ Activa (MCP v1.3.1) |
| 4 | `obtener_galeria_hotel` | Entrega fotos del hotel para soporte comercial | Lee `hotels_master` (gallery) | ✅ Activa |
| 5 | `registrar_lead` | Crea un nuevo lead de ventas en el CRM | Escribe `crm_leads` | ✅ Activa |
| 6 | `avanzar_pipeline` | Cambia el stage de un lead en el embudo | Escribe `crm_leads` + `crm_activities` | ✅ Activa |
| 7 | `registrar_actividad` | Agrega notas o logs al historial del lead | Escribe `crm_activities` | ✅ Activa |
| 8 | `crear_deal` | Convierte cotización en negociación formal | Escribe `crm_deals` | ✅ Activa |
| 9 | `consultar_pipeline` | Obtiene agregaciones del embudo | Lee `crm_leads` + `crm_deals` | ✅ Activa |
| 10 | `analisis_financiero` | Análisis financiero / márgenes para escalamiento | Lee `rates` + cálculos | ✅ Activa (MCP v1.3.1) |
| 11 | `consultar_reserva` | Busca una reserva por término (ref, nombre, email) | Lee `bookings` | ✅ Activa (MCP v1.3.1) |

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
