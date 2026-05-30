# REHIDRATACION.md — Rutina de Arranque del Orquestador
## Hermes Commercial · Aliun Travel SRL

---

## Propósito

Cada vez que Hermes Commercial inicia sesión (o se rehidrata tras idle), ejecuta esta rutina en orden para reconstruir contexto operativo completo.

---

## Secuencia de rehidratación

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

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
