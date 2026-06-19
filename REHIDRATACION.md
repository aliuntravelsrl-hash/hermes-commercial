# REHIDRATACION.md — Rutina de Arranque del Orquestador
## Hermes Commercial · Aliun Travel SRL

---

## Propósito

Cada vez que Hermes Commercial inicia sesión (o se rehidrata tras idle), ejecuta esta rutina en orden para reconstruir contexto operativo completo.

---

## Secuencia de rehidratación

### 0. Estado real en personal_ia (15s) — agregado 18 JUN 2026
```
Consultar: rpc_personal_ia_status() filtrando nombre_agente='Hermes Commercial'
Verificar: mi estado real (online/idle/error), no asumir online por defecto
Verificar: estado de mis 5 sub-agentes (vendedor, cotizador, qa-followup,
           finanzas, qa-auditor) — todos reportan a mi supervisor_id
Verificar: incidentes sin resolver atados a mi empleado_id en logs_operativos
```

### 0b. Mis 12 tools MCP reales (fuente: atlas-sales-mcp/MCP_OWNERSHIP.md) — agregado 18 JUN 2026
```
Flujo de atención (en orden):
1. registrar_lead → 2. buscar_hoteles → 3. consultar_disponibilidad
→ 4. calcular_cotizacion → 5. generar_cotizacion_pdf (enviar landing_url,
NUNCA pdf_url directo) → 6. validar_ocupacion_habitacion (si 3+ pax)
→ 7. calcular_precio_paquete

Pipeline: 8. avanzar_pipeline → 9. registrar_actividad → 10. crear_deal

Consulta: 11. consultar_reserva → 12. validar_comprobante (registra pago
en pending_review — NUNCA confirma el depósito, eso es Director vía
Hermes Ops con registrar_deposito) → obtener_galeria_hotel

⚠️ NUNCA ejecuto registrar_deposito — es exclusivo del Director vía Hermes Ops.
```

### 1. Identidad (30s)
```
Leer: IDENTITY.md → quién soy, qué heredo, mi mandato
```

### 2. Alma comercial (30s)
```
Leer: SOUL.md → mentalidad comercial, temporadas, lectura del mercado
```

### 3. Framework de cierre (20s)
```
Leer: FRAMEWORK.md → 7 leyes Kennedy+Belfort, tabla objeciones
```

### 4. Rutina operativa (20s)
```
Leer: RUTINA.md → 10 estados E1→E10, flujo de venta
```

### 5. Herramientas disponibles (20s)
```
Leer: TOOLS.md → 18 tools (6 nativas + 9 MCP + 3 pendientes WF)
Verificar MCP health: GET https://n8n-atlas-sales-mcp.xaruuo.easypanel.host/health
```

### 6. Routing (15s)
```
Leer: ROUTING.md → 6 departamentos, keywords, despacho
```

### 7. Verificación de servicios (30s)
```
Verificar: Supabase MCP → RPC calcular_precio_paquete (smoke test)
Verificar: Chatwoot → health endpoint
Verificar: n8n → webhook activo
Verificar: WhatsApp → Meta Cloud API token válido
```

### 8. Estado del pipeline CRM (15s)
```
Consultar: consultar_pipeline → leads por etapa, deals abiertos
Identificar: leads sin seguimiento >48h (PRIORIDAD)
```

---

## Total rehidratación: ~3 minutos

---

## Post-rehidratación

Después de rehidratar, el orquestador:

1. **Reporta estado** al Director (Telegram) si es arranque matutino
2. **Procesa leads sin seguimiento** como primera acción
3. **Queda en modo escucha** para nuevos leads por webhook

---

## Si algo falla

| Fallo | Acción |
|-------|--------|
| MCP no responde | Reportar al Director. Usar tools nativas como fallback |
| Supabase RPC error | Reportar columna/función específica. No asumir |
| Chatwoot caído | Responder directo vía Meta Cloud API |
| n8n caído | No se reciben leads. Reportar inmediatamente |
| Token Meta expirado | System User Token no expira (adminsrl). Si falla, regenerar en Meta Dashboard |

## Jerarquía real (confirmado 18 JUN 2026)

Reporto **directamente al Director** (Aldo Hilario) — no a Hermes Ops.
Hermes Ops es la capa de infraestructura, paralela, no superior.

Mis 5 sub-agentes (todos con `supervisor_id` apuntando a mí en `personal_ia`):
- **vendedor** — conversación de ventas (Gemini 2.0 Flash Lite)
- **cotizador** — RPCs + cálculo de precio (Qwen 3.5 Flash)
- **qa-followup** — seguimientos T+2h/24h/48h (Ministral 8B)
- **finanzas** — validación de pagos/depósitos (Qwen 3.6 Flash)
- **qa-auditor** — auditoría de calidad + KPIs (Gemini 2.0 Flash Lite)

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026 · actualizado 18 JUN 2026 (ATLAS-TECH)*
