# knowledge/extracted-intel.md — Inteligencia Heredada Adaptada
## Hermes Commercial · Aliun Travel SRL

---

## Fuente: Paperclip OTA (cantera original)

### Lo que se heredó y se adaptó
- **SOUL §16** → Framework Kennedy+Belfort 7 leyes (ahora en FRAMEWORK.md)
- **RAG vectorial** → Orchestrator con embeddings (patrón conservado, modelo actualizado)
- **Routing de departamentos** → 6 departamentos comerciales (ROUTING.md, sin refs a Paperclip)
- **CRM pipeline** → 5 tools Supabase nativas (sin Kommo dependency)
- **Humanización** → Patrones de delay N1=5min/N2=7.5min/N3=10min (conservado)

### Lo que se descartó
- API Paperclip puertos 4050/4051 (no existe)
- Dependencia de `@paperclip/api` (degradado)
- Marketing tools (generar_post_creativo, copywriter, art_director — NO es dominio Commercial)
- Referencia a Sonnet 4.5 como cabeza (actualizado a Gemini 2.0 Flash)

---

## Fuente: OpenClaw / atlas-sales-v2 (cantera inmediata)

### Lo que se heredó y se adaptó
- **sales_SOUL.md** → SOUL.md (sin refs a Paperclip, sin "OpenClaw" como marca)
- **system_prompt_vendedor_v2.md** → agents/vendedor.md (sin Kommo, sin Paperclip)
- **rutina_vendedor_v2.md** → RUTINA.md (sin refs a workflow Kommo IDs)
- **routing_matrix.js** → config/routing_matrix.js (ESM puro, sin Paperclip deps)
- **sales_TOOLS.md** → TOOLS.md (columnas auditadas, sin asumir)
- **sales_AGENTS.md** → ROUTING.md (Sales Manager → orquestador swarm)

### Lo que se descartó
- Todas las refs a Kommo CRM (degradado)
- Supabase project `oyihiyivdhfxpyiwnmqk` (es el web, no el MCP backend)
- Workflow n8n `0ps4wRmBFXcAy0u2` (legacy, será reemplazado)
- "OpenClaw" como nombre del agente (ahora Hermes Commercial)
- Dependencia de RateHawk/TBO/eJuniper (las RPCs Supabase las reemplazan)

---

## Lecciones aprendidas de la migración

1. **NUNCA asumir columnas de Supabase** — auditar con `information_schema.columns` antes de escribir RPCs
2. **Todos los parámetros RPC usan `p_` prefix** — consistencia con Supabase
3. **`limit` es reserved word en PostgreSQL** — usar `p_limit`
4. **exchange_rates usa `currency_pair/rate_sell`** — NO `from_currency/to_currency/rate`
5. **marketing_offers usa `discount_percentage/is_published`** — NO `discount_percent/published`
6. **rooms usa `capacity_adults/capacity_children/room_type`** — NO `max_adults/max_children`
7. **rates usa `adult_rate/valid_from/valid_to`** — NO `base_price_usd`

---

## Patrón BD Madre→Hijas (vigente)

- Dato actualizado → tabla madre (hotels_master, rates, rooms)
- Registro de actividad → tabla hija INSERT ONLY (crm_activities, atlas_payments)
- Nunca UPDATE en hijas, solo INSERT

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
