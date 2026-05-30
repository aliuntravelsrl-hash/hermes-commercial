# MEMORY.md — Memoria Postgres de Hermes Commercial
## Aliun Travel SRL · 29 MAY 2026

---

## Problema

Sin memoria persistente, Hermes Commercial no puede:
- Recordar qué se dijo con un cliente hace 2 horas
- Saber si ya le cotizó un hotel específico
- Continuar una conversación interrumpida
- Diferenciar entre cliente nuevo y recurrente
- El orquestador despacha al sub-agente sin contexto previo → el sub-agente arranca en blanco

## Solución: 2 tablas nuevas en Supabase

### 1. `conversation_messages` — Historial de conversación

```sql
CREATE TABLE public.conversation_messages (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid NOT NULL,           -- Agrupa mensajes de una sesión
  lead_id       uuid REFERENCES public.crm_leads(id),
  wa_message_id text,                       -- ID del mensaje WhatsApp (wamid)
  direction     text NOT NULL CHECK (direction IN ('inbound', 'outbound')),
  sender_type   text NOT NULL CHECK (sender_type IN ('client', 'agent', 'human', 'system')),
  agent_name    text,                        -- Qué sub-agente respondió (vendedor, cotizador, etc.)
  content       text NOT NULL,
  content_type  text DEFAULT 'text',         -- text, image, document, audio
  media_url     text,                        -- URL del adjunto si hay
  metadata      jsonb DEFAULT '{}',          -- Datos extras (template usado, tool llamada, etc.)
  created_at    timestamptz DEFAULT now()
);

-- Índices para queries frecuentes
CREATE INDEX idx_conv_msgs_conversation ON public.conversation_messages(conversation_id, created_at);
CREATE INDEX idx_conv_msgs_lead ON public.conversation_messages(lead_id, created_at);
CREATE INDEX idx_conv_msgs_created ON public.conversation_messages(created_at DESC);

-- RLS
ALTER TABLE public.conversation_messages ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON public.conversation_messages FOR ALL USING (true);
```

### 2. `client_profiles` — Perfil agregado del cliente

```sql
CREATE TABLE public.client_profiles (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  phone           text UNIQUE NOT NULL,       -- +1809XXXXXXX
  name            text,
  segment         text,                       -- familia, pareja, grupo, luna_de_miel, B2B, mayorista
  preferred_zone  text,                       -- Punta Cana, Bayahibe, Samaná, Bávaro
  budget_level    text DEFAULT 'medium',      -- low, medium, high, premium
  language        text DEFAULT 'es',          -- es, en, fr
  total_conversations integer DEFAULT 0,
  total_bookings  integer DEFAULT 0,
  total_revenue_usd numeric DEFAULT 0,
  last_interaction timestamptz,
  first_interaction timestamptz DEFAULT now(),
  tags            text[] DEFAULT '{}',        -- ['recurrente', 'grupo', 'navideño', etc.]
  notes           text,                        -- Notas del agente/Director
  created_at      timestamptz DEFAULT now(),
  updated_at      timestamptz DEFAULT now()
);

-- Índices
CREATE INDEX idx_client_profiles_phone ON public.client_profiles(phone);
CREATE INDEX idx_client_profiles_segment ON public.client_profiles(segment);
CREATE INDEX idx_client_profiles_last ON public.client_profiles(last_interaction DESC);

-- RLS
ALTER TABLE public.client_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Service role full access" ON public.client_profiles FOR ALL USING (true);
```

---

## Cómo se usa la memoria

### Cuando entra un mensaje nuevo

```
1. Buscar client_profile por phone → si existe, cargar perfil (segmento, preferencias, historial)
2. Buscar conversation_messages por lead_id ORDER BY created_at DESC LIMIT 20 → últimos 20 mensajes
3. Inyectar en el contexto del orquestador:
   - Perfil del cliente (nombre, segmento, presupuesto, hotel favorito)
   - Últimos mensajes de la conversación activa
4. Orquestador despacha al sub-agente CON contexto
5. Sub-agente responde sabiendo qué se dijo antes
```

### Cuando el sub-agente responde

```
1. INSERT en conversation_messages (direction=outbound, agent_name=vendedor, content=respuesta)
2. Si es primera interacción → INSERT en client_profiles
3. Si cliente existe → UPDATE client_profiles (last_interaction, tags si cambiaron)
```

### Contexto inyectado al orquestador

```json
{
  "client": {
    "phone": "+18095551234",
    "name": "María",
    "segment": "familia",
    "budget_level": "medium",
    "total_conversations": 3,
    "total_bookings": 1,
    "tags": ["recurrente", "navideño"]
  },
  "conversation": [
    {"role": "client", "content": "Hola, busco algo para Semana Santa", "time": "10:30"},
    {"role": "agent", "agent": "vendedor", "content": "Hola María! Para cuántas personas?", "time": "10:31"},
    {"role": "client", "content": "Somos 4, 2 adultos 2 niños", "time": "10:33"}
  ],
  "lead": {
    "id": "uuid",
    "stage": "descubrimiento",
    "created_at": "2026-05-30T14:30:00Z"
  }
}
```

---

## RPCs de memoria (agregar al MCP)

### `get_conversation_context(p_phone, p_limit)`

Devuelve perfil del cliente + últimos N mensajes + estado del lead activo. Un solo RPC para inyectar contexto completo al orquestador.

```sql
CREATE OR REPLACE FUNCTION public.get_conversation_context(
  p_phone text,
  p_limit integer DEFAULT 20
)
RETURNS jsonb AS $$
DECLARE
  v_profile jsonb;
  v_messages jsonb;
  v_lead jsonb;
BEGIN
  -- Perfil del cliente
  SELECT row_to_json(p.*)::jsonb INTO v_profile
  FROM public.client_profiles p
  WHERE p.phone = p_phone;

  -- Lead activo
  SELECT row_to_json(l.*)::jsonb INTO v_lead
  FROM public.crm_leads l
  WHERE l.phone = p_phone
    AND l.stage NOT IN ('cerrado', 'perdido')
  ORDER BY l.created_at DESC LIMIT 1;

  -- Últimos mensajes
  SELECT jsonb_agg(row_to_json(m.*)::jsonb ORDER BY m.created_at DESC) INTO v_messages
  FROM (
    SELECT m.* FROM public.conversation_messages m
    WHERE m.lead_id = (v_lead->>'id')::uuid
    ORDER BY m.created_at DESC
    LIMIT p_limit
  ) m;

  RETURN jsonb_build_object(
    'profile', COALESCE(v_profile, '{}'),
    'lead', COALESCE(v_lead, '{}'),
    'messages', COALESCE(v_messages, '[]'::jsonb)
  );
END;
$$ LANGUAGE plpgsql STABLE;
```

### `save_message(p_conversation_id, p_lead_id, p_direction, p_sender_type, p_agent_name, p_content, p_content_type, p_metadata)`

Guarda cada mensaje de la conversación.

```sql
CREATE OR REPLACE FUNCTION public.save_message(
  p_conversation_id uuid,
  p_lead_id uuid,
  p_direction text,
  p_sender_type text,
  p_agent_name text DEFAULT NULL,
  p_content text,
  p_content_type text DEFAULT 'text',
  p_media_url text DEFAULT NULL,
  p_metadata jsonb DEFAULT '{}'
)
RETURNS uuid AS $$
DECLARE
  v_id uuid;
BEGIN
  INSERT INTO public.conversation_messages (
    conversation_id, lead_id, direction, sender_type,
    agent_name, content, content_type, media_url, metadata
  ) VALUES (
    p_conversation_id, p_lead_id, p_direction, p_sender_type,
    p_agent_name, p_content, p_content_type, p_media_url, p_metadata
  ) RETURNING id INTO v_id;
  RETURN v_id;
END;
$$ LANGUAGE plpgsql;
```

---

## Relación con tablas existentes

```
client_profiles (1) ←→ (N) crm_leads
crm_leads (1) ←→ (N) conversation_messages
crm_leads (1) ←→ (N) crm_activities
crm_leads (1) ←→ (1) crm_deals
```

- `client_profiles` es la madre del cliente (actualizable)
- `conversation_messages` es hija INSERT ONLY
- `crm_activities` es hija INSERT ONLY
- `crm_deals` se crea cuando hay intención de cierre

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
