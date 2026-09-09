# MANUAL DE OPERACIÓN Y MAPEO DE VERSIONES (ATLAS-HERMES)
## HERMES COMMERCIAL GATEWAY HTTP · TRAEFIK RE-ROUTING & N8N DESPACHO
**Documento:** `MANUAL-OPERATIVO-HERMES-GATEWAY-HTTP-v2.md`  
**Fecha:** 09 de Septiembre de 2026 · 08:08 (Local Time)  
**Autoridad Soberana:** Director General Aldo Hilario  
**Auditor / Implementador:** Antigravity (ATLAS-TECH / Curator Constitucional)  
**Estado:** ✅ PRODUCCIÓN / VERIFICADO E2E  

---

## 1. RESUMEN EJECUTIVO

Se completó con éxito la exposición pública en Traefik del Gateway HTTP real de Hermes Commercial (`gateway.py`, FastAPI) en el puerto interno `8645`, preservando de forma intacta y sin alteración el acceso al dashboard existente en el puerto `4860`.

Asimismo, se actualizó el nodo `04_HERMES_RESPONDER` en el workflow de n8n `WF-CHATWOOT-HERMES-v1` (`Z6wqgUmmtvupZ5dV`), sustituyendo la lógica estática if/else previa por una llamada HTTP POST dinámica hacia el Gateway de IA de Hermes Commercial, con fallback inteligente y despacho automático hacia Chatwoot/WhatsApp.

---

## 2. MAPEO DE INFRAESTRUCTURA Y PUERTOS (VPS2)

- **Host:** VPS2 (`srv1587803.hstgr.cloud` / `2.24.198.231` / Tailscale `100.105.66.111`)
- **Contenedor:** `hermes-agent-dpkf-hermes-agent-1`
- **Compose Path:** `/docker/hermes-agent-dpkf/docker-compose.yml`
- **Volumen Persistente:** `/docker/hermes-agent-dpkf/data` $\rightarrow$ `/opt/data`

### Enrutamiento Traefik Configurado:

| Router Traefik | Host / Path | Puerto Destino | Función | Estado |
|---|---|---|---|---|
| `hermes-commercial` | `Host(\`hermes.srv1587803.hstgr.cloud\`)` | `4860` | Dashboard TUI / Web Hermes | ✅ 302 Auth OK (Intacto) |
| `hermes-commercial-gateway` | `Host(\`hermes-api.srv1587803.hstgr.cloud\`) \|\| (Host(\`hermes.srv1587803.hstgr.cloud\`) && PathPrefix(\`/chat\`, \`/health\`, \`/docs\`, \`/webhooks\`, \`/api\`))` | `8645` | Gateway HTTP Real FastAPI | ✅ 200 OK Live |

---

## 3. ESPECIFICACIÓN DEL GATEWAY HTTP (`gateway.py`)

- **Ubicación:** `/opt/data/gateway.py`
- **Framework:** FastAPI / Uvicorn en `0.0.0.0:8645`
- **Endpoints Expuestos:**
  1. `GET /health` $\rightarrow$ Retorna estado de salud `{"status":"ok","gateway":"hermes-commercial","port":8645}`.
  2. `POST /chat` & `POST /api/chat` $\rightarrow$ Recibe mensaje, datos del contacto, conv_id, invoca LLM (OpenRouter / NVIDIA) y devuelve `{ ok: true, respuesta: "...", model: "...", agente: "hermes-commercial" }`.
  3. `POST /webhooks/chatwoot-commercial` $\rightarrow$ Webhook directo opcional para Chatwoot con auto-respuesta y logs en Supabase `logs_operativos`.
  4. `GET /docs` $\rightarrow$ Documentación interactiva Swagger UI.

- **Auto-Inicio Resiliente:** Se implementó `/opt/data/entrypoint_wrapper.sh` que garantiza que al reiniciar el contenedor o el VPS, `gateway.py` y `escuchador.py` arrancan automáticamente en background antes del entrypoint principal.

---

## 4. INTEGRACIÓN WORKFLOW N8N (`WF-CHATWOOT-HERMES-v1`)

- **Workflow ID:** `Z6wqgUmmtvupZ5dV`
- **Webhook Inbound:** `https://n8n-n8n.xaruuo.easypanel.host/webhook/chatwoot-hermes`

### Pipeline de Nodos:
1. `01_WEBHOOK_CHATWOOT` (Webhook POST): Recibe evento `message_created` desde Chatwoot.
2. `02_FILTRAR` (Code): Extrae `convId`, `msg`, `contacto`, `telefono`, validando que sea mensaje entrante del viajero.
3. `03_APLICA` (If): Evalúa `skip === false`. Si es skip, responde `07_SKIP_ACK`. Si es válido, avanza.
4. `03B_REGISTRAR_SESION` (HTTP Request): Registra sesión y lead en Supabase RPC `canal_recibir_mensaje`.
5. `04_HERMES_RESPONDER` (HTTP Request): Envía petición `POST https://hermes.srv1587803.hstgr.cloud/chat` con payload `{ message, contacto, telefono, conv_id, session_id, lead_id }`.
6. `04B_FORMAT_HERMES_MSG` (Code): Recibe la respuesta de IA de Hermes y prepara fallback de contingencia en caso de indisponibilidad externa.
7. `05_RESPONDER_CW` (HTTP Request): Publica el mensaje en Chatwoot (`POST /api/v1/accounts/1/conversations/{convId}/messages`).
8. `06_ACK` (Respond to Webhook): Retorna `{"ok": true}` a Chatwoot.

---

## 5. RESULTADOS DE PRUEBAS DE HUMO (E2E)

1. **Healthcheck Traefik:**
   - `GET https://hermes.srv1587803.hstgr.cloud/health` $\rightarrow$ `HTTP 200 OK`
2. **Dashboard Port 4860:**
   - `GET https://hermes.srv1587803.hstgr.cloud/` $\rightarrow$ `HTTP 302 Location: /login`
3. **Endpoint de Inferencia IA:**
   - `POST https://hermes.srv1587803.hstgr.cloud/chat` $\rightarrow$ `HTTP 200 OK` con respuesta generada por LLM (`nvidia/nemotron-3-super-120b-a12b:free`).
4. **Ejecución n8n E2E:**
   - Inbound Chatwoot Webhook $\rightarrow$ Procesado exitosamente en `Execution ID: 93409` con estado `SUCCESS`, despachando la respuesta de Hermes al viajero.
