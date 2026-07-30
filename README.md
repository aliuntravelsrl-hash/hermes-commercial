# Hermes Commercial
> Dominio: **Ventas · CRM · Booking · Pricing · Legal**

## Identidad
**Rol en el swarm:** executor
**Propósito:** Motor de ventas y CRM. Gestiona el pipeline comercial, cotizaciones, reservas y comunicación con clientes de Aliun Travel SRL.

## Dependencias
| Tipo | Fuente |
|------|--------|
| Constitución | [atlas-cos-v1](https://github.com/aliuntravelsrl-hash/atlas-cos-v1) |
| Protocolos activos | TPP-v1 · KBP-v1 · POI-v1 · ONP-v1 · SPI-v1 · SPEC-024 |
| MCP / Herramientas | atlas-sales-mcp · Supabase · Chatwoot · OpenRouter |
| Knowledge Manifest | `atlas-cableados/knowledge/manifests/hermes-commercial.yaml` |

## Fuente Canónica
Toda doctrina, protocolo y especificación vive en **atlas-cos-v1**.
Este repositorio **implementa** — nunca duplica doctrina.

```
atlas-cos-v1 (Constitución)
      │
      ▼
Hermes Commercial
(Implementación de dominio)
```

## Sub-agentes
vendedor · cotizador · finanzas · qa-followup (en migración a hermes-qa)

## Repos relacionados
- `atlas-cos-v1` — fuente canónica del COS
- `atlas-cableados` — rehidratación y knowledge manifests
- `aliun-rrhh-v2` — perfiles RRHH-IA y roles

## Estado
`CONVERGENCIA EN PROGRESO` — REPO-MOD-001 Fase 2

## Últimos cambios
Ver commits del repositorio.

---
*Aliun Travel SRL · Director Aldo Hilario · ATLAS-TECH*
*COS-v3.5 · [atlas-cos-v1](https://github.com/aliuntravelsrl-hash/atlas-cos-v1)*
