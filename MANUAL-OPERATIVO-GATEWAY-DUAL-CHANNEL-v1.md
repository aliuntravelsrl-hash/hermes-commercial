# PROTOCOLO OPERATIVO: ARQUITECTURA DUAL-CHANNEL Y TESTING SANDBOX WHATSAPP
## HERMES COMMERCIAL GATEWAY · BAILEYS BRIDGE & TELEGRAM ORCHESTRATION
**Documento:** `MANUAL-OPERATIVO-GATEWAY-DUAL-CHANNEL-v1.md`
**Fecha:** 03 de Septiembre de 2026 · 10:55 (Local Time)  
**Autoridad Soberana:** Director General Aldo Hilario  
**Curator / Notario:** Antigravity (Computer / Curator Constitucional)  
**Modularidad:** `hermes-gateway` (Puerto 8644), Baileys Bridge (WhatsApp QR) y Telegram Bot API.

---

1. **Arquitectura Dual-Channel Simultánea:**
   - **WhatsApp:** Canal externo de clientes (Inbound de ventas e itinerarios quote/compare).
   - **Telegram:** Canal interno de gobernanza (Alertas, Heartbeats y autorizaciones al Director Chat ID: 683265740).

2. **Protocolo de Testing Sandbox (QR Pairing):**
   - **Fase A (Sandbox PR):** Escanear QR via `tail -f /root/.hermes/whatsapp/bridge.log` con número secundario/du-pruebas. Validar cotización Hotel+Excursión, PDF DOC-1 y seguimientos WH-2 (T+2h/24h/48h).
   - **Fase B (Swap a Producción):** Eliminar `srm -rf /root/.hermes/whatsapp/auth/` y re-escanear con el número oficial de Aliun Travel SRL.

---
*Documento Notariado y Registrado en atlas-curator-office y hermes-commercial.*
