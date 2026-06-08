# TOOLS_SCHEMA.md — Firmas reales del MCP (verificadas en vivo)

**Servidor:** `https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/mcp`
**Versión MCP:** `atlas-sales-tools v1.3.1`
**Verificado:** 08 JUN 2026 (tools/list contra servidor en producción)
**Total tools:** 18 confirmadas

---

## ⚠️ CORRECCIÓN DOCTRINAL CRÍTICA — prefijo `p_`

La capa MCP **NO** usa el prefijo `p_` en sus parámetros. El prefijo `p_` pertenece
a los argumentos internos de las funciones RPC de Supabase, **no** a la interfaz MCP
que el agente invoca.

- ❌ Incorrecto (falla con `-32602 Input validation error`): `consultar_disponibilidad(p_hotel_slug=...)`
- ✅ Correcto: `consultar_disponibilidad(slug=...)`

Verificado en vivo: llamar con `p_hotel_slug` devuelve `expected string, received undefined, path: ["slug"]`.

---

## Firmas reales (parámetros MCP · obligatorios en **negrita**)

| # | Tool | Parámetros (obligatorios en negrita) |
|---|------|--------------------------------------|
| 1 | `consultar_disponibilidad` | **slug**, **check_in**, **check_out**, adults, children |
| 2 | `buscar_hoteles` | **destination**, limit |
| 3 | `generar_cotizacion_pdf` | **slug**, **nombre**, **email**, **check_in**, **check_out**, **habitacion**, **precio_total**, regimen, pasajeros, moneda |
| 4 | `validar_comprobante` | **booking_reference**, **monto_reportado**, descripcion, imagen_url |
| 5 | `obtener_galeria_hotel` | **hotel_slug**, limit |
| 6 | `generar_post_creativo` | **hotel_slug**, channel, offer_id |
| 7 | `calcular_cotizacion` | **hotel_name_query**, **check_in**, **check_out**, adults, children |
| 8 | `analisis_financiero` | **analysis_description**, budget |
| 9 | `calcular_precio_paquete` | **hotel_id**, **noches**, **adultos**, ninos, tasa_venta, es_proveedor_local_dop, modo_productivo |
| 10 | `validar_ocupacion_habitacion` | **hotel_id**, **room_type**, **adultos**, ninos |
| 11 | `buscar_ofertas_marketing` | hotel_slug, offer_type, limit *(ninguno obligatorio)* |
| 12 | `consultar_reserva` | **search_term** |
| 13 | `registrar_deposito` | **booking_reference**, **monto_deposito**, **email_cliente**, metodo_pago, notas |
| 14 | `registrar_lead` | **full_name**, **phone**, **source**, email, hotel_interest, check_in, check_out, adults, children, message |
| 15 | `avanzar_pipeline` | **lead_id**, **new_stage**, actor |
| 16 | `registrar_actividad` | **lead_id**, **type**, **content**, cotizacion_id |
| 17 | `crear_deal` | **lead_id**, **hotel_slug**, **check_in**, **check_out**, **adults**, **total_usd**, children, margin_pct, landing_url, cotizacion_id |
| 18 | `consultar_pipeline` | *(sin parámetros)* |

---

## Notas de tools

- **`calcular_cotizacion`** usa `hotel_name_query` (búsqueda por nombre), distinto de
  `consultar_disponibilidad` que usa `slug` exacto. No son intercambiables.
- **`buscar_hoteles`** opera por `destination`. Históricamente el RPC `buscar_hoteles`
  no existía en Supabase (modo fallback webhook n8n); hoy la tool responde vía MCP.
- **`generar_post_creativo`** existe en el MCP aunque sea de dominio marketing. El repo
  comercial puede no listarla por doctrina, pero está disponible en el servidor.
- **`analisis_financiero`** y **`consultar_reserva`** existen en el MCP y antes no
  estaban documentadas en `TOOLS.md` comercial.

---

## Smoke test E2E (08 JUN 2026)

- `consultar_pipeline` → OK · 760 leads, 3 deals, conversion_rate 0.1, deals: 2 pendiente / 1 depositado
- `consultar_disponibilidad` / `calcular_precio_paquete` → responden (validan esquema correctamente; fallan solo si se usa `p_` legacy)

---

*Hermes Commercial · Aliun Travel SRL · esquema verificado 08 JUN 2026*
