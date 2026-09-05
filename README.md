# Hermes Commercial
> Dominio: **Ventas Omnicanal (WhatsApp & ChatGPT Voice) · CRM · Pricing · Booking**

## Identidad
**Rol en el swarm:** executor (Commercial Runtime)
**Propósito:** Motor de ejecución comercial y orquestador omnicanal. Gestiona el pipeline comercial, cotizaciones determinísticas, reservas, canal de voz en tiempo real y comunicación con clientes de Aliun Travel SRL.

## Dependencias
| Tipo | Fuente |
|------|--------|
| Constitución | [atlas-cos-v1](https://github.com/aliuntravelsrl-hash/atlas-cos-v1) |
| Protocolos activos | TPP-v1 · KBP-v1 · POI-v1 · ONP-v1 · SPI-v1 · SPEC-024 · DUAL-CHANNEL-v1 |
| MCP / Herramientas | atlas-sales-mcp · Supabase · Chatwoot · ChatGPT Voice Gateway · OpenRouter |
| Knowledge Manifest | `atlas-cableados/knowledge/manifests/hermes-commercial.yaml` |
| Autoridad Cambiaria | Misión Control Live (`public.exchange_rates` / `rate_sell`) |

## Fuente Canónica
Toda doctrina, protocolo y especificación vive en **atlas-cos-v1**.
Este repositorio **implementa** — nunca duplica doctrina.

```
atlas-cos-v1 (Constitución)
      │
      ▼
Hermes Commercial
(Implementación de dominio comercial)
```

## Sub-agentes
- `vendedor`: Conversación de ventas, construcción de valor y diálogo en tiempo real de voz.
- `cotizador`: Cálculo determinístico de precios y RPCs de inventario.
- `finanzas`: Validación de comprobantes y emisión de alerta interactiva al Director General.
- `qa-followup`: Cadencia de seguimientos automatizados T+2h/24h/48h.
- `qa-auditor`: Auditoría interna de calidad comercial.

## Repos relacionados
- `atlas-cos-v1` — fuente canónica del COS
- `Ariadne-Data` — SSOT de datos y analítica
- `atlas-intel` — radar de paridad y pre-check XML
- `hermes-qa` — certificación de fulfillment y auditoría legal F6
- `atlas-cableados` — rehidratación y knowledge manifests

## Estado
`CONVERGENCIA TO-BE COMPLETADA` — COS-v3.5 Omnicanal

---
*Aliun Travel SRL · Director Aldo Hilario · ATLAS-TECH*
*COS-v3.5 · [atlas-cos-v1](https://github.com/aliuntravelsrl-hash/atlas-cos-v1)*

