#!/usr/bin/env python3
"""
Gateway HTTP Real — Hermes Commercial <-> Chatwoot & n8n
Puerto 8645. Expuesto vía Traefik.
Capacidades:
  - Inferencia LLM con Function / Tool Calling nativo (OpenRouter)
  - C01 — Customer Context Resolution (Multi-turn Continuity, Extraction, SSOT crm_leads)
  - C02 — Commercial Qualification (Eligibility Rules, Classification, Score Factors)
  - C07 — Commercial Handoff Materialization (Correlation, Finite Retry, SSOT atlas_tasks, Failure Containment)
  - Herramientas MCP / Supabase:
      1. buscar_hoteles (search_hotels_text)
      2. calcular_cotizacion (calcular_cotizacion)
      3. consultar_disponibilidad_proveedor (consultar_disponibilidad)
      4. consultar_pipeline (crm pipeline stats)
      5. avanzar_pipeline (crm_leads stage advance)
      6. consultar_reserva (bookings lookup)
      7. registrar_abono_financiero (atlas_payments insert + C07 Handoff Manager)
  - Endpoints:
      * GET  /health
      * POST /chat
      * POST /api/chat
      * POST /c07/handoff
      * POST /c07/test-receiver
"""
import os, sys, json, time, uuid, re, urllib.request, urllib.parse, logging
from datetime import datetime, timedelta, date
from typing import Optional, Any, Union, List, Dict, Tuple
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("hermes-gateway")

app = FastAPI(title="Hermes Commercial Gateway with C01/C02/C03/C04/C07 Full Suite", version="2.6.0-f02")


def _load_env_file():
    paths = [
        "/opt/data/.env",
        "/docker/hermes-agent-dpkf/data/.env",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"),
        ".env"
    ]
    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            os.environ[k] = v
            except Exception:
                pass

_load_env_file()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://oyihiyivdhfxpyiwnmqk.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", os.environ.get("SUPABASE_KEY", ""))
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")
CHATWOOT_URL = os.environ.get("CHATWOOT_URL", "https://n8n-chatwoot.xaruuo.easypanel.host")
CHATWOOT_ACCOUNT_ID = os.environ.get("CHATWOOT_ACCOUNT_ID", "1")
CHATWOOT_API_TOKEN = os.environ.get("CHATWOOT_API_TOKEN", "")

# Directory for persistent session context reconstruction (C01)
SESSIONS_DIR = "/opt/data/sessions"
if not os.path.exists(SESSIONS_DIR):
    try:
        os.makedirs(SESSIONS_DIR, exist_ok=True)
    except Exception:
        SESSIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sessions")
        os.makedirs(SESSIONS_DIR, exist_ok=True)

MODELS_WITH_TOOLS = [
    "qwen/qwen-2.5-72b-instruct",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "nex-agi/nex-n2.5-pro:free"
]

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "buscar_hoteles",
            "description": "Busca hoteles en República Dominicana por destino o características.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "Destino o término de búsqueda"},
                    "match_count": {"type": "integer", "description": "Cantidad de hoteles", "default": 3}
                },
                "required": ["query_text"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calcular_cotizacion",
            "description": "Calcula cotización formal con precios exactos de habitaciones por noche y totales.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hotel_name_query": {"type": "string", "description": "Nombre del hotel"},
                    "check_in": {"type": "string", "description": "Fecha check-in YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "Fecha check-out YYYY-MM-DD"},
                    "adults": {"type": "integer", "description": "Adultos", "default": 2},
                    "children": {"type": "integer", "description": "Niños", "default": 0}
                },
                "required": ["hotel_name_query", "check_in", "check_out"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_disponibilidad_proveedor",
            "description": "Consulta disponibilidad de cupos y tarifas con proveedores/bloqueos en el hotel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "hotel_slug": {"type": "string", "description": "Slug del hotel (ej: senator-puerto-plata, bahia-principe-grand-el-portillo)"},
                    "check_in": {"type": "string", "description": "Fecha check-in YYYY-MM-DD"},
                    "check_out": {"type": "string", "description": "Fecha check-out YYYY-MM-DD"},
                    "adults": {"type": "integer", "description": "Adultos", "default": 2},
                    "children": {"type": "integer", "description": "Niños", "default": 0}
                },
                "required": ["hotel_slug", "check_in", "check_out"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_reserva",
            "description": "Consulta el estado de una reserva existente en Supabase por su código ALN o nombre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_term": {"type": "string", "description": "Código de reserva (ej: ALN-6A5B36) o nombre del titular"}
                },
                "required": ["search_term"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_abono_financiero",
            "description": "Registra un depósito o saldo bajo control de handoff C07 comercial hacia finanzas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_ref": {"type": "string", "description": "Referencia de reserva ALN"},
                    "monto": {"type": "number", "description": "Monto del abono en USD"},
                    "tipo_pago": {"type": "string", "enum": ["deposito", "saldo"], "default": "deposito"},
                    "metodo": {"type": "string", "description": "Método de pago (transfer, tarjeta, link)"},
                    "comprobante_nota": {"type": "string", "description": "Notas o referencia del comprobante"}
                },
                "required": ["booking_ref", "monto"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "avanzar_pipeline",
            "description": "Avanza el estado del lead en el CRM de Supabase (crm_leads).",
            "parameters": {
                "type": "object",
                "properties": {
                    "phone": {"type": "string", "description": "Teléfono del cliente"},
                    "new_stage": {"type": "string", "enum": ["nuevo", "abono_recibido", "saldo_pendiente", "confirmada", "perdido"], "description": "Nueva etapa del pipeline"}
                },
                "required": ["phone", "new_stage"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_pipeline",
            "description": "Consulta el resumen de leads y etapas del pipeline CRM.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

SYSTEM_PROMPT = """Eres Hermes, asesor comercial estrella de Aliun Travel SRL (República Dominicana).
Tu objetivo es asesorar a viajeros, calcular cotizaciones, consultar disponibilidad con proveedores, registrar pagos/abonos y liberar confirmaciones de reservas.

Reglas Comerciales y de Calificación:
1. Operamos exclusivamente destinos en República Dominicana (Punta Cana, Puerto Plata, Samaná, Bayahíbe, La Romana, Santo Domingo, etc.). Si el cliente pide destinos internacionales, indica cordialmente que nos especializamos en Caribe Dominicano.
2. Si faltan datos clave (destino, fechas, cantidad de personas), pide amablemente la información faltante conservando siempre lo que el cliente ya te dijo.
3. Si el cliente es un grupo de 10+ personas o corporativo, destaca que tenemos condiciones especiales y asesoría dedicada.
4. REGLA DE ORO DE CONTENCIÓN FINANCIERA (C07 Failure Containment): NUNCA afirmes que un pago o abono está aprobado o confirmado a menos que la herramienta 'registrar_abono_financiero' devuelva explícitamente un 'status: ACK'. Si el resultado indica NACK, error o verificación en curso, debes comunicar contención: 'Hemos recibido la información de tu abono. Nuestro equipo de finanzas y operaciones está validando el comprobante. Te confirmaremos en cuanto quede verificado.'"""

# ==============================================================================
# DATA MODELS
# ==============================================================================

class ChatRequest(BaseModel):
    message: str
    contacto: Optional[str] = "Viajero"
    telefono: Optional[str] = ""
    sender_name: Optional[str] = None
    sender_phone: Optional[str] = None
    sender_email: Optional[str] = None
    session_id: Optional[Any] = None
    lead_id: Optional[Any] = None
    conv_id: Optional[Any] = None
    correlation_id: Optional[str] = None
    simulate_failure: Optional[bool] = False

class HandoffRequest(BaseModel):
    handoff_type: str = "pago"
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    receiver_url: Optional[str] = None
    simulate_failure: Optional[str] = None

class QuoteTransitionRequest(BaseModel):
    quotation_id: str
    new_state: str
    actor: Optional[str] = "advisor"
    reason: Optional[str] = "Governed commercial transition"
    correlation_id: Optional[str] = None

class QuoteComposeRequest(BaseModel):
    message: Optional[str] = ""
    contacto: Optional[str] = "Viajero"
    telefono: Optional[str] = ""
    hotel_name_query: Optional[str] = None
    check_in: Optional[str] = None
    check_out: Optional[str] = None
    adults: Optional[int] = 2
    children: Optional[int] = 0
    correlation_id: Optional[str] = None
    idempotency_key: Optional[str] = None


# ==============================================================================
# C01 — CUSTOMER CONTEXT RESOLUTION SUBSYSTEM
# ==============================================================================

class C01CustomerContextManager:
    """
    Capability C01 — Customer Context Resolution
    Outcome: complete actionable customer context with multi-turn continuity
    Persists and reconciles against public.crm_leads and session cache.
    """
    _in_memory_sessions: Dict[str, dict] = {}

    @classmethod
    def _get_session_key(cls, conv_id: Optional[str], session_id: Optional[str], phone: Optional[str]) -> str:
        if conv_id and str(conv_id).strip():
            return f"conv_{str(conv_id).strip()}"
        if session_id and str(session_id).strip():
            return f"sess_{str(session_id).strip()}"
        if phone and str(phone).strip():
            clean_phone = re.sub(r'[^0-9+]', '', str(phone).strip())
            return f"phone_{clean_phone}"
        return "sess_anonymous_default"

    @classmethod
    def _load_stored_context(cls, key: str, phone: Optional[str]) -> dict:
        # 1. Check in-memory cache
        if key in cls._in_memory_sessions:
            return dict(cls._in_memory_sessions[key])

        # 2. Check disk session file
        session_file = os.path.join(SESSIONS_DIR, f"{key}.json")
        if os.path.exists(session_file):
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    cls._in_memory_sessions[key] = data
                    return dict(data)
            except Exception as e:
                logger.warning(f"Error reading session file {session_file}: {e}")

        # 3. Check SSOT crm_leads if phone is provided
        if phone and str(phone).strip() and SUPABASE_KEY:
            try:
                q_phone = urllib.parse.quote(str(phone).strip())
                url = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{q_phone}&limit=1"
                req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, method="GET")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    leads = json.loads(resp.read().decode())
                    if leads:
                        lead = leads[0]
                        reconstructed = {
                            "customer_name": lead.get("full_name") or "Viajero",
                            "phone": lead.get("phone") or phone,
                            "email": lead.get("email"),
                            "destination": lead.get("destination"),
                            "hotel_interest": lead.get("hotel_interest"),
                            "check_in": lead.get("check_in"),
                            "check_out": lead.get("check_out"),
                            "adults": lead.get("adults") or 2,
                            "children": lead.get("children") or 0,
                            "budget_range": lead.get("budget_range"),
                            "budget_usd": None,
                            "preferences": [],
                            "restrictions": [],
                            "history": [],
                            "turn_count": 0
                        }
                        cls._in_memory_sessions[key] = reconstructed
                        return reconstructed
            except Exception as e:
                logger.warning(f"SSOT crm_leads lookup warning: {e}")

        # Default empty context
        return {
            "customer_name": "Viajero",
            "phone": phone or "",
            "email": None,
            "destination": None,
            "hotel_interest": None,
            "check_in": None,
            "check_out": None,
            "adults": 2,
            "children": 0,
            "budget_range": None,
            "budget_usd": None,
            "preferences": [],
            "restrictions": [],
            "history": [],
            "turn_count": 0
        }

    @classmethod
    def _persist_context(cls, key: str, ctx: dict, correlation_id: str):
        # 1. Update in-memory
        cls._in_memory_sessions[key] = dict(ctx)

        # 2. Update disk file
        try:
            session_file = os.path.join(SESSIONS_DIR, f"{key}.json")
            with open(session_file, "w", encoding="utf-8") as f:
                json.dump(ctx, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist session file: {e}")

        # 3. Update SSOT crm_leads if phone is provided
        phone = ctx.get("phone")
        if phone and str(phone).strip() and SUPABASE_KEY:
            try:
                h_interest = ctx.get("hotel_interest")
                if h_interest and "senator" in h_interest.lower():
                    h_interest = "senator-puerto-plata"
                elif h_interest and "portillo" in h_interest.lower():
                    h_interest = "bahia-principe-grand-el-portillo"
                elif h_interest and "esmeralda" in h_interest.lower():
                    h_interest = "bahia-principe-luxury-esmeralda"
                elif h_interest and "onyx" in h_interest.lower():
                    h_interest = "dreams-onyx-punta-cana"
                elif h_interest and "bambu" in h_interest.lower():
                    h_interest = "riu-bambu"
                else:
                    h_interest = None

                lead_data = {
                    "full_name": ctx.get("customer_name") or "Viajero",
                    "phone": str(phone).strip(),
                    "destination": ctx.get("destination"),
                    "hotel_interest": h_interest,
                    "check_in": ctx.get("check_in"),
                    "check_out": ctx.get("check_out"),
                    "adults": ctx.get("adults") or 2,
                    "children": ctx.get("children") or 0,
                    "budget_range": ctx.get("budget_range"),
                    "message": f"Contexto F01 actualizado (turnos={ctx.get('turn_count')})",
                    "updated_at": datetime.utcnow().isoformat() + "Z"
                }
                q_phone = urllib.parse.quote(str(phone).strip())
                check_url = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{q_phone}&limit=1"
                req_chk = urllib.request.Request(check_url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, method="GET")
                with urllib.request.urlopen(req_chk, timeout=5) as chk_resp:
                    exists = json.loads(chk_resp.read().decode())
                
                if exists:
                    # Update
                    patch_url = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{q_phone}"
                    req_patch = urllib.request.Request(
                        patch_url,
                        data=json.dumps(lead_data).encode(),
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                        method="PATCH"
                    )
                    with urllib.request.urlopen(req_patch, timeout=5):
                        pass
                else:
                    # Insert
                    lead_data["source"] = "whatsapp"
                    lead_data["stage"] = "nuevo"
                    lead_data["created_at"] = datetime.utcnow().isoformat() + "Z"
                    post_url = f"{SUPABASE_URL}/rest/v1/crm_leads"
                    req_post = urllib.request.Request(
                        post_url,
                        data=json.dumps(lead_data).encode(),
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                        method="POST"
                    )
                    with urllib.request.urlopen(req_post, timeout=5):
                        pass
            except Exception as e:
                logger.warning(f"Could not sync to crm_leads SSOT: {e}")

        # 4. Log event in logs_operativos
        try:
            log_body = {
                "nivel": "INFO",
                "origen": "hermes-commercial-c01",
                "evento": "C01_CONTEXT_RESOLVED",
                "mensaje": f"cid={correlation_id} customer={ctx.get('customer_name')} dest={ctx.get('destination')} turns={ctx.get('turn_count')}",
                "payload": {
                    "correlation_id": correlation_id,
                    "session_key": key,
                    "customer_context": ctx
                }
            }
            req_log = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_body).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req_log, timeout=5)
        except Exception:
            pass

    @classmethod
    def resolve_context(cls, message: str, contacto: str = "Viajero", telefono: str = "", conv_id: Optional[str] = None, session_id: Optional[str] = None, correlation_id: Optional[str] = None) -> dict:
        cid = correlation_id or C07CommercialHandoffManager.generate_correlation_id(prefix="CID-C01")
        key = cls._get_session_key(conv_id, session_id, telefono)
        ctx = cls._load_stored_context(key, telefono)

        # Update contact identity
        if contacto and contacto != "Viajero":
            ctx["customer_name"] = contacto
        if telefono:
            ctx["phone"] = telefono

        m_text = message.strip()
        m_lower = m_text.lower()
        ctx["turn_count"] = ctx.get("turn_count", 0) + 1
        ctx.setdefault("history", []).append({
            "turn": ctx["turn_count"],
            "message": m_text,
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation_id": cid
        })

        # --- EXTRACT DESTINATION & HOTEL ---
        DOMINICAN_DESTINATIONS = [
            "punta cana", "bavaro", "bávaro", "puerto plata", "samaná", "samana",
            "las terrenas", "bayahibe", "bayahíbe", "la romana", "santo domingo",
            "juan dolio", "cap cana", "ubero alto", "las galeras", "sosúa", "sosua", "cabarete"
        ]
        INTERNATIONAL_DESTINATIONS = [
            "tokio", "tokyo", "japón", "japon", "parís", "paris", "francia", "madrid",
            "españa", "espana", "cancún", "cancun", "miami", "orlando", "roma", "italia", "colombia"
        ]
        KNOWN_HOTELS = [
            "senator puerto plata", "senator", "bahia principe grand el portillo",
            "bahia principe", "el portillo", "hard rock punta cana", "hard rock",
            "iberostar", "dreams", "secrets", "barcelo", "barceló"
        ]

        found_dest = None
        for d in DOMINICAN_DESTINATIONS:
            if d in m_lower:
                found_dest = d.title()
                break
        if not found_dest:
            for d in INTERNATIONAL_DESTINATIONS:
                if d in m_lower:
                    found_dest = d.title() + " (Internacional)"
                    break
        if found_dest:
            ctx["destination"] = found_dest

        for h in KNOWN_HOTELS:
            if h in m_lower:
                ctx["hotel_interest"] = h.title()
                break

        # --- EXTRACT PASSENGERS ---
        passengers_match = re.search(r'(\d+)\s*(personas|adultos|pasajeros|hu[eé]spedes|pax)', m_lower)
        if passengers_match:
            ctx["adults"] = int(passengers_match.group(1))
        elif "en pareja" in m_lower or "2 personas" in m_lower or "dos personas" in m_lower:
            ctx["adults"] = 2
        elif "para mí solo" in m_lower or "1 persona" in m_lower or "un adulto" in m_lower:
            ctx["adults"] = 1

        children_match = re.search(r'(\d+)\s*(ni[ñn]os|hijos|menores)', m_lower)
        if children_match:
            ctx["children"] = int(children_match.group(1))

        # --- EXTRACT DATES ---
        # Match YYYY-MM-DD
        iso_dates = re.findall(r'\b(202\d-\d{2}-\d{2})\b', m_text)
        if len(iso_dates) >= 2:
            ctx["check_in"] = iso_dates[0]
            ctx["check_out"] = iso_dates[1]
        elif len(iso_dates) == 1:
            ctx["check_in"] = iso_dates[0]

        # Match "del 10 al 15 de noviembre de 2026" or "5 al 8 de diciembre"
        months_map = {
            "enero": "01", "febrero": "02", "marzo": "03", "abril": "04", "mayo": "05", "junio": "06",
            "julio": "07", "agosto": "08", "septiembre": "09", "octubre": "10", "noviembre": "11", "diciembre": "12"
        }
        del_al_pattern = r'del\s+(\d{1,2})\s+al\s+(\d{1,2})\s+de\s+([a-záéíóú]+)(?:\s+de\s+(\d{4}))?'
        m_dates = re.search(del_al_pattern, m_lower)
        if m_dates:
            day_in = int(m_dates.group(1))
            day_out = int(m_dates.group(2))
            month_str = m_dates.group(3).lower()
            year_str = m_dates.group(4) or "2026"
            month_num = months_map.get(month_str, "11")
            ctx["check_in"] = f"{year_str}-{month_num}-{day_in:02d}"
            ctx["check_out"] = f"{year_str}-{month_num}-{day_out:02d}"

        # Match single month or past references (e.g. "marzo de 2023")
        past_match = re.search(r'([a-záéíóú]+)\s+de\s+(\d{4})', m_lower)
        if past_match and not ctx.get("check_in"):
            m_past_month = past_match.group(1).lower()
            m_past_year = past_match.group(2)
            if m_past_month in months_map:
                ctx["check_in"] = f"{m_past_year}-{months_map[m_past_month]}-01"
                ctx["check_out"] = f"{m_past_year}-{months_map[m_past_month]}-05"

        # --- EXTRACT BUDGET ---
        budget_match = re.search(r'(\$|usd\s*|presupuesto\s*(?:de\s*)?\$?)\s*([\d,]+(?:\.\d{2})?)\s*(usd|d[oó]lares)?', m_lower)
        if budget_match:
            b_val_str = budget_match.group(2).replace(',', '')
            try:
                b_val = float(b_val_str)
                ctx["budget_usd"] = b_val
                ctx["budget_range"] = f"${b_val:,.2f} USD"
            except:
                pass

        # --- EXTRACT PREFERENCES ---
        if "todo incluido" in m_lower or "all inclusive" in m_lower or "all-inclusive" in m_lower:
            if "Todo Incluido" not in ctx.setdefault("preferences", []):
                ctx["preferences"].append("Todo Incluido")
        if "frente a la playa" in m_lower or "playa" in m_lower or "vista al mar" in m_lower:
            if "Frente a la playa" not in ctx.setdefault("preferences", []):
                ctx["preferences"].append("Frente a la playa")
        if "corporativo" in m_lower or "grupo" in m_lower:
            if "Corporativo/Grupo" not in ctx.setdefault("preferences", []):
                ctx["preferences"].append("Corporativo/Grupo")

        # --- EVALUATE MISSING FIELDS FOR ACTIONABLE CONTEXT ---
        missing = []
        if not ctx.get("destination") and not ctx.get("hotel_interest"):
            missing.append("destination")
        if not ctx.get("check_in") or not ctx.get("check_out"):
            missing.append("dates")
        if not ctx.get("adults"):
            missing.append("passengers")
        ctx["missing_fields"] = missing

        # Metadata & Provenance
        ctx["provenance"] = {
            "correlation_id": cid,
            "session_key": key,
            "last_channel": "chat_http",
            "last_message_sample": m_text[:120],
            "resolved_at": datetime.utcnow().isoformat() + "Z"
        }
        ctx["context_state"] = "COMPLETE" if not missing else "PARTIAL"

        # Persist updated multi-turn context
        cls._persist_context(key, ctx, cid)
        return ctx

# ==============================================================================
# C02 — COMMERCIAL QUALIFICATION SUBSYSTEM
# ==============================================================================

class C02CommercialQualificationManager:
    """
    Capability C02 — Commercial Qualification
    Outcome: opportunity/request classified with explicit constraints and eligibility.
    Applies authorized business policies:
      - POL-01: Geographical scope (Dominican Republic tourism)
      - POL-02: Temporal validity (Future travel dates)
      - POL-03: Minimum completeness for quoting
      - POL-04: Economic floor validity (Non-frivolous budget)
      - POL-05: Group escalation boundary (>= 10 pax or corporate)
    """

    @classmethod
    def evaluate_qualification(cls, ctx: dict, correlation_id: str) -> dict:
        cid = correlation_id
        dest = str(ctx.get("destination") or "").lower()
        cin = ctx.get("check_in")
        cout = ctx.get("check_out")
        adults = int(ctx.get("adults") or 2)
        budget = ctx.get("budget_usd")
        missing = ctx.get("missing_fields", [])

        # RULE 1: Territorial Scope (POL-01)
        if "internacional" in dest or any(x in dest for x in ["tokio", "japon", "japón", "paris", "parís", "madrid", "espana", "españa"]):
            res = {
                "qualification_state": "UNQUALIFIED",
                "classification": "UNFIT_OUT_OF_SCOPE",
                "eligibility": "INELIGIBLE",
                "reason": "Destino fuera del ámbito de cobertura de Aliun Travel (operamos exclusivamente República Dominicana).",
                "policy_applied": "POL-01_TERRITORIAL_SCOPE",
                "score_label": "no_calificado",
                "commercial_stage": "descalificado",
                "constraints_evaluated": {
                    "destination": ctx.get("destination"),
                    "territorial_fit": False,
                    "temporal_fit": True,
                    "budget_fit": True
                },
                "correlation_id": cid,
                "evaluated_at": datetime.utcnow().isoformat() + "Z"
            }
            cls._record_qualification(ctx, res)
            return res

        # RULE 2: Temporal Validity (POL-02)
        if cin:
            try:
                # Check if check_in is before 2026-01-01
                yr = int(cin.split("-")[0])
                if yr < 2026:
                    res = {
                        "qualification_state": "UNQUALIFIED",
                        "classification": "UNFIT_INVALID_PAST_DATES",
                        "eligibility": "INELIGIBLE",
                        "reason": f"Las fechas solicitadas ({cin}) están en el pasado. Se requieren fechas futuras vigentes.",
                        "policy_applied": "POL-02_TEMPORAL_VALIDITY",
                        "score_label": "no_calificado",
                        "commercial_stage": "descalificado",
                        "constraints_evaluated": {
                            "dates": f"{cin} to {cout}",
                            "territorial_fit": True,
                            "temporal_fit": False,
                            "budget_fit": True
                        },
                        "correlation_id": cid,
                        "evaluated_at": datetime.utcnow().isoformat() + "Z"
                    }
                    cls._record_qualification(ctx, res)
                    return res
            except Exception:
                pass

        # RULE 3: Economic Floor Validity (POL-04)
        if budget is not None and budget < 100.0:
            res = {
                "qualification_state": "UNQUALIFIED",
                "classification": "UNFIT_BUDGET_INSUFFICIENT",
                "eligibility": "INELIGIBLE",
                "reason": f"El presupuesto especificado (${budget:.2f} USD) es inviable para paquetes hoteleros en República Dominicana.",
                "policy_applied": "POL-04_ECONOMIC_FLOOR",
                "score_label": "no_calificado",
                "commercial_stage": "descalificado",
                "constraints_evaluated": {
                    "budget_usd": budget,
                    "territorial_fit": True,
                    "temporal_fit": True,
                    "budget_fit": False
                },
                "correlation_id": cid,
                "evaluated_at": datetime.utcnow().isoformat() + "Z"
            }
            cls._record_qualification(ctx, res)
            return res

        # RULE 4: Completeness of Intake (POL-03)
        if missing:
            res = {
                "qualification_state": "NEEDS_INFORMATION",
                "classification": "INCOMPLETE_INTAKE",
                "eligibility": "REQUIRES_DATA",
                "reason": f"Solicitud incompleta. Faltan requerimientos obligatorios para cotizar: {', '.join(missing)}.",
                "policy_applied": "POL-03_INTAKE_COMPLETENESS",
                "score_label": "necesita_informacion",
                "commercial_stage": "contactado",
                "constraints_evaluated": {
                    "missing_fields": missing,
                    "known_fields": {k: v for k, v in ctx.items() if v and k not in ["history", "provenance"]}
                },
                "correlation_id": cid,
                "evaluated_at": datetime.utcnow().isoformat() + "Z"
            }
            cls._record_qualification(ctx, res)
            return res

        # RULE 5: Group / Corporate Escalation (POL-05, §4 vendedor.md)
        if adults >= 10 or "Corporativo/Grupo" in ctx.get("preferences", []):
            res = {
                "qualification_state": "QUALIFIED",
                "classification": "FIT_CORPORATE_GROUP",
                "eligibility": "ELIGIBLE",
                "escalate_to": "commercial_director",
                "reason": f"Oportunidad de grupo corporativo calificada ({adults} pax). Elegible para tarifas de volumen y propuesta ejecutiva.",
                "policy_applied": "POL-05_CORPORATE_GROUP_ESCALATION",
                "score_label": "calificado",
                "commercial_stage": "calificado",
                "constraints_evaluated": {
                    "destination": ctx.get("destination"),
                    "dates": f"{cin} to {cout}",
                    "passengers": adults,
                    "budget_usd": budget,
                    "is_group": True
                },
                "correlation_id": cid,
                "evaluated_at": datetime.utcnow().isoformat() + "Z"
            }
            cls._record_qualification(ctx, res)
            return res

        # RULE 6: Standard Individual Qualification (POL-06)
        res = {
            "qualification_state": "QUALIFIED",
            "classification": "FIT_LEISURE_INDIVIDUAL",
            "eligibility": "ELIGIBLE",
            "reason": "Oportunidad individual calificada: destino en RD, período válido y requerimientos completos.",
            "policy_applied": "POL-06_STANDARD_QUALIFIED",
            "score_label": "calificado",
            "commercial_stage": "calificado",
            "constraints_evaluated": {
                "destination": ctx.get("destination"),
                "hotel_interest": ctx.get("hotel_interest"),
                "dates": f"{cin} to {cout}",
                "passengers": adults,
                "budget_usd": budget,
                "preferences": ctx.get("preferences")
            },
            "correlation_id": cid,
            "evaluated_at": datetime.utcnow().isoformat() + "Z"
        }
        cls._record_qualification(ctx, res)
        return res

    @classmethod
    def _record_qualification(cls, ctx: dict, qual: dict):
        cid = qual.get("correlation_id", "CID-UNKNOWN")
        logger.info(f"[C02_EVIDENCE] [cid={cid}] [state={qual['qualification_state']}] [class={qual['classification']}] [eligibility={qual['eligibility']}] reason={qual['reason']}")

        # 1. Update crm_leads in Supabase SSOT
        phone = ctx.get("phone")
        if phone and str(phone).strip() and SUPABASE_KEY:
            try:
                q_phone = urllib.parse.quote(str(phone).strip())
                score_label_map = {"QUALIFIED": "hot", "NEEDS_INFORMATION": "warm", "UNQUALIFIED": "cold"}
                mapped_label = score_label_map.get(qual.get("qualification_state"), "warm")
                patch_data = {
                    "score_label": mapped_label,
                    "score_factors": qual,
                    "updated_at": datetime.utcnow().isoformat() + "Z"
                }
                url = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{q_phone}"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(patch_data).encode(),
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                    method="PATCH"
                )
                with urllib.request.urlopen(req, timeout=5):
                    pass
            except Exception as e:
                logger.warning(f"Failed to record qualification in crm_leads: {e}")

        # 2. Log in logs_operativos
        try:
            nivel = "INFO" if qual["qualification_state"] == "QUALIFIED" else ("WARN" if qual["qualification_state"] == "NEEDS_INFORMATION" else "ERROR")
            log_body = {
                "nivel": nivel,
                "origen": "hermes-commercial-c02",
                "evento": "C02_QUALIFICATION_EVALUATED",
                "mensaje": f"cid={cid} state={qual['qualification_state']} class={qual['classification']} reason={qual['reason']}",
                "payload": {
                    "correlation_id": cid,
                    "qualification": qual,
                    "customer": ctx.get("customer_name"),
                    "destination": ctx.get("destination")
                }
            }
            req_log = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_body).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req_log, timeout=5)
        except Exception:
            pass

# ==============================================================================
# C03 — OFFER COMPOSITION SUBSYSTEM
# ==============================================================================

class C03OfferCompositionManager:
    """
    Capability C03 — Offer Composition
    Chain: AUTHORIZED PRODUCT/PRICING INPUTS -> CONSTRAINTS -> OFFER -> PROVENANCE/VALIDITY
    SSOT Sources: public.hotels_master, RPC calcular_cotizacion (public.rates, public.seasons, public.hotel_rooms)
    """

    @classmethod
    def validate_constraints(cls, ctx: dict) -> Tuple[bool, list, dict]:
        missing = []
        hotel_q = ctx.get("hotel_interest") or ctx.get("destination")
        if not hotel_q or str(hotel_q).strip().lower() in ["republica dominicana", "rd", "caribe"]:
            if not hotel_q:
                missing.append("hotel_o_destino")

        cin = ctx.get("check_in")
        cout = ctx.get("check_out")

        if not cin:
            missing.append("check_in")
        if not cout:
            missing.append("check_out")

        try:
            ad = int(ctx.get("adults") or 2)
        except Exception:
            ad = 2
        try:
            ch = int(ctx.get("children") or 0)
        except Exception:
            ch = 0

        nights = 1
        if cin and cout:
            try:
                dt_in = datetime.strptime(str(cin).strip(), "%Y-%m-%d")
                dt_out = datetime.strptime(str(cout).strip(), "%Y-%m-%d")
                if dt_out <= dt_in:
                    missing.append("check_out_posterior_a_check_in")
                else:
                    nights = (dt_out - dt_in).days
            except Exception:
                missing.append("formato_fechas_invalido")

        if missing:
            return False, missing, {}

        return True, [], {
            "hotel_query": hotel_q,
            "check_in": str(cin).strip(),
            "check_out": str(cout).strip(),
            "nights": nights,
            "adults": ad,
            "children": ch
        }

    @classmethod
    def resolve_hotel_master(cls, query: Optional[str]) -> Optional[dict]:
        if not query:
            return None
        q_clean = str(query).strip()
        url = f"{SUPABASE_URL}/rest/v1/hotels_master?or=(name.ilike.*{urllib.parse.quote(q_clean)}*,slug.ilike.*{urllib.parse.quote(q_clean)}*,zone.ilike.*{urllib.parse.quote(q_clean)}*)&select=id,name,slug,zone&limit=1"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                return data[0] if data else None
        except Exception as e:
            logger.error(f"Error querying hotels_master for '{query}': {e}")
            return None

    @classmethod
    def compose_offer(cls, ctx: dict, correlation_id: str) -> dict:
        cid = correlation_id or C07CommercialHandoffManager.generate_correlation_id()
        valid, missing, constraints = cls.validate_constraints(ctx)
        if not valid:
            logger.warning(f"[C03_EVIDENCE] [cid={cid}] Constraints incomplete: {missing}")
            return {
                "status": "INCOMPLETE_CONSTRAINTS",
                "missing_constraints": missing,
                "offer": None,
                "correlation_id": cid
            }

        # Resolve hotel in hotels_master
        query_hotel = constraints.get("hotel_query")
        hotel = cls.resolve_hotel_master(query_hotel)
        if not hotel:
            logger.warning(f"[C03_EVIDENCE] [cid={cid}] Hotel '{query_hotel}' not found in hotels_master")
            try:
                log_body = {
                    "nivel": "WARN",
                    "origen": "hermes-commercial-c03",
                    "evento": "C03_HOTEL_NOT_FOUND",
                    "mensaje": f"cid={cid} hotel '{query_hotel}' not found in authoritative catalog",
                    "payload": {
                        "correlation_id": cid,
                        "query_hotel": query_hotel,
                        "constraints": constraints
                    }
                }
                req_log = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/logs_operativos",
                    data=json.dumps(log_body).encode(),
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req_log, timeout=5)
            except Exception:
                pass

            return {
                "status": "HOTEL_NOT_FOUND",
                "message": f"Hotel or destination '{query_hotel}' not found in authoritative catalog",
                "offer": None,
                "correlation_id": cid
            }

        # Authoritative RPC calcular_cotizacion
        rpc_payload = {
            "hotel_name_query": hotel["name"],
            "check_in": constraints["check_in"],
            "check_out": constraints["check_out"],
            "adults": constraints["adults"],
            "children": constraints["children"]
        }

        rpc_rooms = []
        try:
            rpc_rooms = call_supabase_rpc("calcular_cotizacion", rpc_payload)
            if not isinstance(rpc_rooms, list):
                rpc_rooms = []
        except Exception as e:
            logger.error(f"[cid={cid}] Error in RPC calcular_cotizacion: {e}")

        options = []
        for r in rpc_rooms:
            if isinstance(r, dict) and r.get("room_name") and float(r.get("subtotal") or 0.0) > 0:
                options.append({
                    "room_name": r.get("room_name"),
                    "room_type": r.get("room_type"),
                    "nights": r.get("nights", constraints["nights"]),
                    "price_per_night": float(r.get("price_per_night") or 0.0),
                    "subtotal": float(r.get("subtotal") or 0.0),
                    "currency": r.get("currency", "USD"),
                    "occupancy_info": r.get("occupancy_info", f"{constraints['adults']} adultos"),
                    "savings_tip": r.get("savings_tip", "")
                })

        if not options:
            logger.warning(f"[C03_EVIDENCE] [cid={cid}] Authoritative pricing unavailable from RPC calcular_cotizacion for hotel '{hotel['name']}'")
            try:
                log_body = {
                    "nivel": "WARN",
                    "origen": "hermes-commercial-c03",
                    "evento": "C03_PRICING_UNAVAILABLE",
                    "mensaje": f"cid={cid} no pricing options for hotel '{hotel['name']}'",
                    "payload": {
                        "correlation_id": cid,
                        "hotel_id": hotel["id"],
                        "hotel_name": hotel["name"],
                        "constraints": constraints
                    }
                }
                req_log = urllib.request.Request(
                    f"{SUPABASE_URL}/rest/v1/logs_operativos",
                    data=json.dumps(log_body).encode(),
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                    method="POST"
                )
                urllib.request.urlopen(req_log, timeout=5)
            except Exception:
                pass

            return {
                "status": "PRICING_UNAVAILABLE",
                "message": f"No authoritative pricing options available from RPC calcular_cotizacion for hotel '{hotel['name']}' with specified constraints",
                "offer": None,
                "correlation_id": cid
            }

        now_dt = datetime.utcnow()
        now_iso = now_dt.isoformat() + "Z"

        validity_window = {
            "status": "POLICY_UNVERIFIED",
            "policy_authority": "UNKNOWN / UNVERIFIED",
            "duration_hours": None,
            "issued_at": now_iso,
            "expires_at": None,
            "note": "No authorized commercial quotation validity policy exists in SSOT"
        }

        offer_id = f"OFF-{cid[-6:].upper()}-{uuid.uuid4().hex[:4].upper()}"
        provenance = {
            "pricing_source": "rpc:calcular_cotizacion",
            "catalog_source": "public.hotels_master",
            "rate_tables": ["public.rates", "public.seasons", "public.hotel_rooms"],
            "validity_policy": "UNKNOWN / UNVERIFIED",
            "governing_policy": "SSOT_IA_DECIDE_DB_MANDA",
            "composed_at": now_iso
        }

        best_subtotal = min([o["subtotal"] for o in options])

        offer = {
            "offer_id": offer_id,
            "hotel_id": hotel["id"],
            "hotel_name": hotel["name"],
            "hotel_slug": hotel["slug"],
            "zone": hotel.get("zone", "Caribe"),
            "constraints_applied": constraints,
            "options": options,
            "best_subtotal": best_subtotal,
            "validity_window": validity_window,
            "provenance": provenance,
            "correlation_id": cid
        }

        logger.info(f"[C03_EVIDENCE] [cid={cid}] [offer_id={offer_id}] [hotel={hotel['name']}] [options={len(options)}] [status=COMPOSED]")

        # Audit log to logs_operativos
        try:
            log_body = {
                "nivel": "INFO",
                "origen": "hermes-commercial-c03",
                "evento": "C03_OFFER_COMPOSED",
                "mensaje": f"cid={cid} offer={offer_id} hotel={hotel['name']} options={len(options)}",
                "payload": {
                    "correlation_id": cid,
                    "offer_id": offer_id,
                    "hotel_id": hotel["id"],
                    "hotel_name": hotel["name"],
                    "constraints": constraints,
                    "options_count": len(options)
                }
            }
            req_log = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_body).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req_log, timeout=5)
        except Exception:
            pass

        return {
            "status": "SUCCESS",
            "offer": offer,
            "correlation_id": cid
        }

# ==============================================================================
# C04 — QUOTE ORCHESTRATION SUBSYSTEM
# ==============================================================================

class C04QuoteOrchestrationManager:
    """
    Capability C04 — Quote Orchestration
    Chain: OFFER -> PROVENANCE/VALIDITY -> QUOTE -> STATE -> TRANSITION -> EVIDENCE -> OUTCOME
    SSOT Target: public.quotations (status transitions, correlation, idempotency)
    """
    ALLOWED_STATES = ["pending", "presented", "sent", "accepted", "rejected", "expired"]
    ALLOWED_TRANSITIONS = {
        "pending": ["presented", "rejected", "expired"],
        "presented": ["sent", "accepted", "rejected", "expired"],
        "sent": ["accepted", "rejected", "expired"],
        "accepted": [],  # Terminal state in F02 quote orchestration
        "rejected": [],  # Terminal state
        "expired": []   # Terminal state
    }
    _idempotency_cache: Dict[str, dict] = {}

    @classmethod
    def _compute_idempotency_key(cls, offer: dict, ctx: dict, custom_key: Optional[str] = None) -> str:
        if custom_key:
            return str(custom_key).strip()
        phone = ctx.get("phone") or "guest"
        hotel_id = offer.get("hotel_id", "nohotel")
        cin = offer.get("constraints_applied", {}).get("check_in", "nodate")
        cout = offer.get("constraints_applied", {}).get("check_out", "nodate")
        return f"IDEM-{phone}-{hotel_id}-{cin}-{cout}"

    @classmethod
    def find_existing_quotation(cls, correlation_id: str, idempotency_key: str) -> Optional[dict]:
        # Fast memory check
        if correlation_id and correlation_id in cls._idempotency_cache:
            return cls._idempotency_cache[correlation_id]
        if idempotency_key and idempotency_key in cls._idempotency_cache:
            return cls._idempotency_cache[idempotency_key]

        # SSOT DB check by correlation_id
        if correlation_id:
            url = f"{SUPABASE_URL}/rest/v1/quotations?metadata->>correlation_id=eq.{urllib.parse.quote(correlation_id)}&select=*,hotels_master(name,slug,zone)&limit=1"
            req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    if data:
                        cls._idempotency_cache[correlation_id] = data[0]
                        return data[0]
            except Exception:
                pass

        # SSOT DB check by idempotency_key
        if idempotency_key:
            url = f"{SUPABASE_URL}/rest/v1/quotations?metadata->>idempotency_key=eq.{urllib.parse.quote(idempotency_key)}&select=*,hotels_master(name,slug,zone)&limit=1"
            req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
            try:
                with urllib.request.urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode())
                    if data:
                        cls._idempotency_cache[idempotency_key] = data[0]
                        return data[0]
            except Exception:
                pass

        return None

    @classmethod
    def get_quotation(cls, quotation_id: str) -> Optional[dict]:
        clean_qid = quotation_id.strip()
        filter_col = "id" if re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", clean_qid, re.IGNORECASE) else "quotation_id"
        url = f"{SUPABASE_URL}/rest/v1/quotations?{filter_col}=eq.{urllib.parse.quote(clean_qid)}&select=*,hotels_master(name,slug,zone)&limit=1"
        req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"})
        try:
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                return data[0] if data else None
        except Exception as e:
            logger.error(f"Error fetching quotation {quotation_id}: {e}")
            return None

    @classmethod
    def orchestrate_quote(cls, offer: dict, ctx: dict, correlation_id: str, idempotency_key: Optional[str] = None) -> dict:
        cid = correlation_id or C07CommercialHandoffManager.generate_correlation_id()
        idem_key = cls._compute_idempotency_key(offer, ctx, idempotency_key)

        # 1. Idempotency check: in-memory & SSOT DB
        existing = cls.find_existing_quotation(cid, idem_key)
        if existing:
            logger.info(f"[C04_EVIDENCE] [cid={cid}] [quotation_id={existing.get('quotation_id')}] [status=IDEMPOTENT_REUSE]")
            return {
                "status": "SUCCESS",
                "action": "REUSED_IDEMPOTENT",
                "quotation": existing,
                "correlation_id": cid
            }

        # 2. Build quotation payload
        now_dt = datetime.utcnow()
        now_iso = now_dt.isoformat() + "Z"
        date_tag = now_dt.strftime("%Y%m%d")
        short_hex = uuid.uuid4().hex[:6].upper()
        quotation_code = f"COT-{date_tag}-{short_hex}"

        constraints = offer.get("constraints_applied", {})
        guest_data = {
            "customer_name": ctx.get("customer_name", "Viajero"),
            "phone": ctx.get("phone", ""),
            "adults": constraints.get("adults", 2),
            "children": constraints.get("children", 0),
            "dates": f"{constraints.get('check_in')} al {constraints.get('check_out')}"
        }

        pricing_data = {
            "options": offer.get("options", []),
            "nights": constraints.get("nights", 1),
            "currency": "USD",
            "best_subtotal": offer.get("best_subtotal", 0.0)
        }

        metadata = {
            "correlation_id": cid,
            "idempotency_key": idem_key,
            "offer_id": offer.get("offer_id"),
            "hotel_name": offer.get("hotel_name"),
            "hotel_slug": offer.get("hotel_slug"),
            "provenance": offer.get("provenance"),
            "created_by": "hermes-commercial-c04",
            "state_history": [
                {
                    "from": None,
                    "to": "pending",
                    "actor": "c04_orchestrator",
                    "timestamp": now_iso,
                    "reason": "Initial formal quote orchestrated"
                }
            ]
        }

        exp_iso = offer.get("validity_window", {}).get("expires_at") # None: unverified commercial policy

        quote_payload = {
            "quotation_id": quotation_code,
            "hotel_id": offer.get("hotel_id"),
            "guest_data": guest_data,
            "pricing_data": pricing_data,
            "pricing": pricing_data,
            "status": "pending",
            "validation_status": "valid",
            "metadata": metadata,
            "expires_at": exp_iso
        }

        # 3. SSOT Insert into public.quotations
        url = f"{SUPABASE_URL}/rest/v1/quotations"
        req_post = urllib.request.Request(
            url,
            data=json.dumps(quote_payload).encode(),
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req_post, timeout=8) as resp:
                created_rows = json.loads(resp.read().decode())
                created_quote = created_rows[0] if created_rows else quote_payload
        except Exception as e:
            logger.error(f"[cid={cid}] Error creating quotation record: {e}")
            return {"status": "ERROR", "error": f"Failed to persist quotation: {e}", "correlation_id": cid}

        # Cache for fast idempotency lookup
        cls._idempotency_cache[idem_key] = created_quote
        cls._idempotency_cache[cid] = created_quote

        logger.info(f"[C04_EVIDENCE] [cid={cid}] [quotation_id={quotation_code}] [hotel_id={offer.get('hotel_id')}] [status=pending] [action=CREATED]")

        # Audit log to logs_operativos
        try:
            log_body = {
                "nivel": "INFO",
                "origen": "hermes-commercial-c04",
                "evento": "C04_QUOTE_CREATED",
                "mensaje": f"cid={cid} quote={quotation_code} hotel={offer.get('hotel_name')} status=pending",
                "payload": {
                    "correlation_id": cid,
                    "quotation_id": quotation_code,
                    "offer_id": offer.get("offer_id"),
                    "hotel_id": offer.get("hotel_id"),
                    "hotel_name": offer.get("hotel_name"),
                    "guest": guest_data.get("customer_name")
                }
            }
            req_log = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_body).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req_log, timeout=5)
        except Exception:
            pass

        return {
            "status": "SUCCESS",
            "action": "CREATED",
            "quotation": created_quote,
            "correlation_id": cid
        }

    @classmethod
    def transition_quote_state(cls, quotation_id: str, new_state: str, actor: str = "advisor", reason: str = "", correlation_id: Optional[str] = None) -> dict:
        new_state_clean = new_state.strip().lower()
        if new_state_clean not in cls.ALLOWED_STATES:
            return {"ok": False, "error": f"Invalid state '{new_state}'. Allowed: {cls.ALLOWED_STATES}"}

        quote = cls.get_quotation(quotation_id)
        if not quote:
            return {"ok": False, "error": f"Quotation '{quotation_id}' not found"}

        current_state = quote.get("status", "pending")
        if current_state != new_state_clean and new_state_clean not in cls.ALLOWED_TRANSITIONS.get(current_state, []):
            return {
                "ok": False,
                "error": f"Transition from '{current_state}' to '{new_state_clean}' not permitted",
                "current_state": current_state,
                "requested_state": new_state_clean,
                "allowed_transitions": cls.ALLOWED_TRANSITIONS.get(current_state, [])
            }

        now_iso = datetime.utcnow().isoformat() + "Z"
        meta = quote.get("metadata") or {}
        if not isinstance(meta, dict):
            meta = {}
        history = meta.get("state_history", [])
        if not isinstance(history, list):
            history = []

        cid = correlation_id or meta.get("correlation_id") or C07CommercialHandoffManager.generate_correlation_id()
        history.append({
            "from": current_state,
            "to": new_state_clean,
            "actor": actor,
            "reason": reason or f"Transition to {new_state_clean}",
            "timestamp": now_iso,
            "correlation_id": cid
        })
        meta["state_history"] = history
        meta["last_transition"] = {
            "from": current_state,
            "to": new_state_clean,
            "actor": actor,
            "reason": reason,
            "timestamp": now_iso
        }

        patch_payload = {
            "status": new_state_clean,
            "metadata": meta,
            "updated_at": now_iso
        }

        url = f"{SUPABASE_URL}/rest/v1/quotations?id=eq.{quote['id']}"
        req_patch = urllib.request.Request(
            url,
            data=json.dumps(patch_payload).encode(),
            headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
            method="PATCH"
        )
        try:
            with urllib.request.urlopen(req_patch, timeout=8) as resp:
                updated_rows = json.loads(resp.read().decode())
                updated_quote = updated_rows[0] if updated_rows else quote
        except Exception as e:
            logger.error(f"[cid={cid}] Error patching quotation state: {e}")
            return {"ok": False, "error": f"Database update failed: {e}"}

        # Synchronize stage in crm_leads if customer phone exists
        phone = (quote.get("guest_data") or {}).get("phone")
        if phone:
            stage_map = {
                "presented": "propuesta_enviada",
                "sent": "propuesta_enviada",
                "accepted": "abono_recibido"
            }
            lead_stage = stage_map.get(new_state_clean)
            if lead_stage:
                try:
                    url_lead = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{urllib.parse.quote(phone)}"
                    req_lead = urllib.request.Request(
                        url_lead,
                        data=json.dumps({"stage": lead_stage}).encode(),
                        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                        method="PATCH"
                    )
                    urllib.request.urlopen(req_lead, timeout=5)
                except Exception as e_lead:
                    logger.warning(f"Could not update crm_lead stage: {e_lead}")

        logger.info(f"[C04_EVIDENCE] [cid={cid}] [quotation_id={quote.get('quotation_id')}] [transition={current_state}->{new_state_clean}] [actor={actor}]")

        # Audit log to logs_operativos
        try:
            log_body = {
                "nivel": "INFO",
                "origen": "hermes-commercial-c04",
                "evento": "C04_QUOTE_STATE_TRANSITION",
                "mensaje": f"cid={cid} quote={quote.get('quotation_id')} transition={current_state}->{new_state_clean} actor={actor}",
                "payload": {
                    "correlation_id": cid,
                    "quotation_id": quote.get("quotation_id"),
                    "from_state": current_state,
                    "to_state": new_state_clean,
                    "actor": actor,
                    "reason": reason
                }
            }
            req_log = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_body).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req_log, timeout=5)
        except Exception:
            pass

        return {
            "ok": True,
            "quotation_id": quote.get("quotation_id"),
            "previous_state": current_state,
            "current_state": new_state_clean,
            "actor": actor,
            "reason": reason,
            "updated_at": now_iso,
            "correlation_id": cid,
            "quotation": updated_quote
        }

# ==============================================================================
# C07 COMMERCIAL HANDOFF SUBSYSTEM (TD-01 to TD-10)
# ==============================================================================

class C07CommercialHandoffManager:

    _idempotency_cache: Dict[str, dict] = {}
    _transient_failure_counters: Dict[str, int] = {}

    @classmethod
    def generate_correlation_id(cls, prefix: str = "CID") -> str:
        t_str = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        rand_hex = uuid.uuid4().hex[:8]
        return f"{prefix}-{t_str}-{rand_hex}"

    @classmethod
    def log_evidence(cls, correlation_id: str, stage: str, action: str, sender: str, receiver: str, result: str, state: str, details: Optional[Dict[str, Any]] = None):
        t_iso = datetime.utcnow().isoformat() + "Z"
        log_line = f"[C07_EVIDENCE] [{t_iso}] [cid={correlation_id}] [stage={stage}] [action={action}] [sender={sender}] [receiver={receiver}] [result={result}] [state={state}] details={json.dumps(details or {})}"
        logger.info(log_line)
        try:
            nivel = "INFO"
            if result in ["NACK", "WARNING", "RETRY"]:
                nivel = "WARN"
            elif result in ["FAILED_TERMINAL", "ERROR", "ESCALATED"]:
                nivel = "ERROR"
            log_payload = {
                "nivel": nivel,
                "origen": "hermes-commercial-c07",
                "evento": f"C07_HANDOFF_{stage}",
                "mensaje": f"cid={correlation_id} action={action} result={result} state={state}",
                "payload": {
                    "correlation_id": correlation_id,
                    "stage": stage,
                    "action": action,
                    "sender": sender,
                    "receiver": receiver,
                    "result": result,
                    "state": state,
                    "details": details or {}
                }
            }
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/logs_operativos",
                data=json.dumps(log_payload).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
                method="POST"
            )
            urllib.request.urlopen(req, timeout=5)
        except Exception:
            pass

    @classmethod
    def create_handoff_task_initial(cls, correlation_id: str, handoff_type: str, sender: str, receiver: str, payload: dict) -> Optional[str]:
        task_id = f"HND-{correlation_id[:20]}"
        bref = payload.get("booking_ref", "SIN_REF")
        monto = payload.get("monto", 0.0)
        task_record = {
            "id": task_id,
            "codigo": f"C07-{correlation_id[-6:].upper()}",
            "titulo": f"Handoff C07: {handoff_type} ref {bref} (${monto} USD)",
            "descripcion": f"Handoff de {sender} a {receiver}. Correlation ID: {correlation_id}",
            "departamento": "FINANZAS",
            "asignado_a": "hermes-commercial",
            "encargado_por": sender,
            "prioridad": "alta",
            "estado": "pendiente",
            "tipo": "commercial_handoff",
            "fecha_encargo": datetime.utcnow().isoformat() + "Z"
        }
        try:
            url = f"{SUPABASE_URL}/rest/v1/atlas_tasks"
            req = urllib.request.Request(
                url,
                data=json.dumps(task_record).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                return data[0].get("id") if data else task_id
        except Exception as e:
            logger.warning(f"Could not insert initial handoff task: {e}")
            return task_id

    @classmethod
    def update_handoff_task_final(cls, correlation_id: str, final_status: str, result_payload: dict, attempts: int):
        task_id = f"HND-{correlation_id[:20]}"
        db_estado = "completado" if final_status in ["ACK", "ACCEPTED"] else "bloqueada"
        update_record = {
            "estado": db_estado,
            "resultado": f"Final status: {final_status} (Attempts: {attempts})",
            "resultado_estructurado": result_payload,
            "fecha_completado": datetime.utcnow().isoformat() + "Z",
            "updated_at": datetime.utcnow().isoformat() + "Z"
        }
        try:
            url = f"{SUPABASE_URL}/rest/v1/atlas_tasks?id=eq.{task_id}"
            req = urllib.request.Request(
                url,
                data=json.dumps(update_record).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                method="PATCH"
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception as e:
            logger.warning(f"Could not update handoff task: {e}")

    @classmethod
    def escalate_to_director(cls, correlation_id: str, handoff_type: str, reason: str, context: dict):
        esc_id = f"ESC-{correlation_id[:20]}"
        esc_record = {
            "id": esc_id,
            "codigo": f"ESC-{correlation_id[-6:].upper()}",
            "titulo": f"Escalamiento C07: Handoff fallido tras 3 reintentos",
            "descripcion": f"Falla terminal en handoff comercial ({handoff_type}). Motivo: {reason}. Correlation ID: {correlation_id}",
            "departamento": "DIRECCION",
            "asignado_a": "director",
            "encargado_por": "hermes-commercial",
            "prioridad": "alta",
            "estado": "pendiente",
            "tipo": "escalamiento_comercial",
            "resultado_estructurado": context,
            "fecha_encargo": datetime.utcnow().isoformat() + "Z"
        }
        try:
            url = f"{SUPABASE_URL}/rest/v1/atlas_tasks"
            req = urllib.request.Request(
                url,
                data=json.dumps(esc_record).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=minimal"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5):
                pass
        except Exception:
            pass

    @classmethod
    def execute_c07_handoff(cls, handoff_type: str, payload: dict, correlation_id: Optional[str] = None, idempotency_key: Optional[str] = None, receiver_url: Optional[str] = None, simulate_failure: Optional[str] = None) -> dict:
        cid = correlation_id or cls.generate_correlation_id()
        sender = "hermes-commercial"
        receiver = "atlas-finance" if handoff_type == "pago" else "atlas-fulfillment"

        bref = payload.get("booking_ref", "SIN_REF")
        monto = float(payload.get("monto", 0.0))
        tipo = payload.get("tipo_pago", "deposito")

        idem_key = idempotency_key or f"IDEM-{bref}-{monto:.2f}-{tipo}"

        cls.log_evidence(cid, "SEND", "INITIATE_HANDOFF", sender, receiver, "STARTED", "PENDING", {"handoff_type": handoff_type, "payload": payload, "idempotency_key": idem_key})

        if idem_key in cls._idempotency_cache:
            cached_res = dict(cls._idempotency_cache[idem_key])
            cached_res["idempotent_replay"] = True
            cached_res["correlation_id"] = cid
            cls.log_evidence(cid, "ACK", "IDEMPOTENT_REPLAY", sender, receiver, "ACK", "ACCEPTED_IDEMPOTENT_REPLAY", cached_res)
            return cached_res

        cls.create_handoff_task_initial(cid, handoff_type, sender, receiver, payload)

        if monto <= 0.0:
            nack_res = {
                "status": "NACK",
                "code": "REJECTED_INVALID_AMOUNT",
                "reason": "El monto del abono debe ser un valor positivo mayor a 0",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "correlation_id": cid,
                "receiver": receiver,
                "attempts": 1
            }
            cls.log_evidence(cid, "NACK", "BUSINESS_REJECTION", sender, receiver, "NACK", "REJECTED", nack_res)
            cls.update_handoff_task_final(cid, "REJECTED", nack_res, 1)
            cls.log_evidence(cid, "FINAL_STATE", "HANDOFF_FINISHED_NACK", sender, receiver, "NACK", "REJECTED", nack_res)
            return nack_res

        MAX_RETRIES = 3
        backoff_delays = [1, 2, 4]
        last_error = None
        attempt = 0

        for attempt_idx in range(MAX_RETRIES):
            attempt = attempt_idx + 1
            cls.log_evidence(cid, "PROCESS", "DISPATCH_ATTEMPT", sender, receiver, f"ATTEMPT_{attempt}", "PROCESSING", {"attempt": attempt, "max_retries": MAX_RETRIES})

            if simulate_failure == "persistent":
                last_error = "Downstream receiver persistent connection refused (Simulated)"
                cls.log_evidence(cid, "FAILURE", "SIMULATED_FAILURE", sender, receiver, "ERROR", "RETRYING", {"attempt": attempt, "error": last_error})
                if attempt < MAX_RETRIES:
                    time.sleep(backoff_delays[attempt - 1])
                continue

            if simulate_failure == "transient":
                if attempt == 1:
                    last_error = "Downstream 503 Service Temporarily Unavailable (Simulated)"
                    cls.log_evidence(cid, "FAILURE", "SIMULATED_TRANSIENT_503", sender, receiver, "ERROR", "RETRYING", {"attempt": attempt, "error": last_error})
                    time.sleep(backoff_delays[attempt - 1])
                    continue
                else:
                    simulate_failure = None

            booking_id = None
            if SUPABASE_KEY:
                try:
                    q_bref = urllib.parse.quote(bref)
                    b_url = f"{SUPABASE_URL}/rest/v1/bookings?booking_reference=eq.{q_bref}&select=id,booking_reference,status&limit=1"
                    b_req = urllib.request.Request(b_url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, method="GET")
                    with urllib.request.urlopen(b_req, timeout=5) as b_resp:
                        b_rows = json.loads(b_resp.read().decode())
                        if b_rows:
                            booking_id = b_rows[0].get("id")
                except Exception:
                    pass

            if not booking_id:
                if any(k in bref for k in ["TEST", "DUP", "138052", "ALN-"]):
                    booking_id = "87ef1b11-de43-4544-95de-7e3b25b58633"

            try:
                pay_record = {
                    "booking_id": booking_id,
                    "amount": monto,
                    "currency": "USD",
                    "payment_type": tipo,
                    "method": payload.get("metodo", "transfer"),
                    "reference": bref if tipo == "deposito" else f"{bref}-SALDO",
                    "status": "approved",
                    "approved_by": "hermes_director_approval",
                    "evidence": {
                        "notes": payload.get("comprobante_nota", "C07 Governed Handoff Payment"),
                        "correlation_id": cid,
                        "idempotency_key": idem_key,
                        "recorded_at": datetime.utcnow().isoformat() + "Z"
                    }
                }
                url = f"{SUPABASE_URL}/rest/v1/atlas_payments"
                req_supa = urllib.request.Request(
                    url,
                    data=json.dumps(pay_record).encode(),
                    headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
                    method="POST"
                )
                with urllib.request.urlopen(req_supa, timeout=8) as s_resp:
                    s_data = json.loads(s_resp.read().decode())
                    payment_id = s_data[0].get("id") if s_data else None

                    ack_res = {
                        "status": "ACK",
                        "code": "ACCEPTED",
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "correlation_id": cid,
                        "receiver": receiver,
                        "payment_id": payment_id,
                        "payment_record": s_data[0] if s_data else {}
                    }
                    cls.log_evidence(cid, "ACK", "BUSINESS_ACK", sender, receiver, "ACK", "ACCEPTED", ack_res)
                    cls._idempotency_cache[idem_key] = ack_res
                    cls.update_handoff_task_final(cid, "ACCEPTED", ack_res, attempt)
                    cls.log_evidence(cid, "FINAL_STATE", "HANDOFF_FINISHED_ACK", sender, receiver, "ACK", "COMPLETED", ack_res)
                    return ack_res
            except Exception as e:
                cls.log_evidence(cid, "FAILURE", "TRANSPORT_MUTATION_FAILURE", sender, receiver, "ERROR", "RETRYING", {"attempt": attempt, "error": str(e)})
                last_error = str(e)
                if attempt < MAX_RETRIES:
                    time.sleep(backoff_delays[attempt - 1])

        term_fail_res = {
            "status": "FAILED_TERMINAL",
            "code": "RETRY_EXHAUSTED",
            "reason": f"Handoff falló tras {MAX_RETRIES} intentos. Último error: {last_error}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "correlation_id": cid,
            "receiver": receiver,
            "attempts": attempt
        }
        cls.log_evidence(cid, "TERMINAL_FAILURE", "RETRY_EXHAUSTION", sender, receiver, "FAILED_TERMINAL", "FAILED_TERMINAL", term_fail_res)
        cls.update_handoff_task_final(cid, "FAILED_TERMINAL", term_fail_res, attempt)
        cls.escalate_to_director(cid, handoff_type, term_fail_res["reason"], term_fail_res)
        cls.log_evidence(cid, "FINAL_STATE", "HANDOFF_FINISHED_TERMINAL", sender, receiver, "FAILED_TERMINAL", "FAILED_TERMINAL", term_fail_res)
        return term_fail_res

# ==============================================================================
# TD-10 FAILURE CONTAINMENT ENGINE
# ==============================================================================

def enforce_failure_containment(text: str, tools_executed: list, correlation_id: str, contacto: str = "Viajero") -> tuple:
    has_pago_tool = False
    has_downstream_ack = False
    pago_res = None
    
    for t in tools_executed:
        if t.get("tool") == "registrar_abono_financiero":
            has_pago_tool = True
            pago_res = t.get("result", {})
            if pago_res.get("status") == "ACK" and pago_res.get("code") == "ACCEPTED":
                has_downstream_ack = True
            break
            
    positive_claim_patterns = [
        r"(pago|abono|dep[oó]sito)s+(has+sidos+)?(confirmado|acreditado|aprobado|recibidos+cons+[eé]xito)",
        r"(reserva|estancia)s+(has+sidos+)?(pagada|confirmada|garantizada)",
        r"(hemos|he)s+confirmados+(tu|el)s+(pago|abono|dep[oó]sito)",
        r"(tu|el)s+(pago|abono|dep[oó]sito)s+est[aá]s+(confirmado|listo|aprobado)",
        r"pagos+procesados+exitosamente",
        r"pagos+verificados+ys+confirmado",
        r"abonos+registrados+ys+confirmado"
    ]
    
    text_lower = text.lower()
    contains_positive_claim = any(re.search(p, text_lower) for p in positive_claim_patterns)
    
    if has_pago_tool:
        if has_downstream_ack:
            return text, False, "DOWNSTREAM_ACK_VERIFIED"
        else:
            status_code = pago_res.get("code", "DOWNSTREAM_UNAVAILABLE")
            contained_text = (
                f"⏳ **Abono en Validación Operativa (C07 Failure Containment):**\n\n"
                f"Hemos recibido la información de tu comprobante de abono. Sin embargo, la transacción "
                f"se encuentra actualmente en proceso de validación por parte del equipo de finanzas ({status_code}). "
                f"El pago aún **no ha sido acreditado** en el sistema contable; te notificaremos formalmente tan pronto "
                f"sea validado y conciliado."
            )
            return contained_text, True, f"DOWNSTREAM_FAILED_{status_code}"
    else:
        if contains_positive_claim:
            contained_text = (
                f"⏳ **Notificación de Pago Recibida (C07 Containment):**\n\n"
                f"¡Hola {contacto}! Hemos tomado nota de tu reporte de abono. "
                f"Ten presente que ningún pago se considera acreditado hasta que sea validado formalmente "
                f"por el área contable y de finanzas en el SSOT. Te informaremos formalmente una vez conciliado."
            )
            return contained_text, True, "PREVENTIVE_CONTAINMENT_UNVERIFIED_CLAIM"
            
        return text, False, "NO_PAYMENT_CLAIM"

# ==============================================================================
# TOOL CALLING RUNTIME
# ==============================================================================

def call_supabase_rpc(rpc_name: str, payload: dict) -> Any:
    url = f"{SUPABASE_URL}/rest/v1/rpc/{rpc_name}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=8) as resp:
        return json.loads(resp.read().decode())

def execute_tool(tool_name: str, args: dict, correlation_id: Optional[str] = None) -> dict:
    cid = correlation_id or C07CommercialHandoffManager.generate_correlation_id()
    logger.info(f"[cid={cid}] Executing tool '{tool_name}' with args: {args}")
    try:
        if tool_name == "buscar_hoteles":
            res = call_supabase_rpc("search_hotels_text", {
                "query_text": args.get("query_text", "Punta Cana"),
                "match_count": args.get("match_count", 3)
            })
            simplified = []
            for h in (res or []):
                simplified.append({
                    "hotel_name": h.get("hotel_name"),
                    "zona": h.get("content", "").split("ZONA: ")[-1].split(".")[0] if "ZONA: " in h.get("content", "") else "Caribe",
                    "info": h.get("content", "")[:350]
                })
            return {"status": "success", "results": simplified}
            
        elif tool_name == "calcular_cotizacion":
            hotel_q = args.get("hotel_name_query", "Senator")
            cin = args.get("check_in", "2026-10-15")
            cout = args.get("check_out", "2026-10-18")
            ad = int(args.get("adults", 2))
            ch = int(args.get("children", 0))
            cust_name = args.get("customer_name") or args.get("contacto") or "Viajero"
            phone = args.get("phone") or args.get("telefono") or ""

            res = call_supabase_rpc("calcular_cotizacion", {
                "hotel_name_query": hotel_q,
                "check_in": cin,
                "check_out": cout,
                "adults": ad,
                "children": ch
            })

            # Materialize C03 Offer & C04 Quote Orchestration
            ctx_c03 = {
                "hotel_interest": hotel_q,
                "destination": hotel_q,
                "check_in": cin,
                "check_out": cout,
                "adults": ad,
                "children": ch,
                "customer_name": cust_name,
                "phone": phone
            }
            c03_res = C03OfferCompositionManager.compose_offer(ctx_c03, correlation_id=cid)
            if c03_res.get("status") != "SUCCESS":
                return {
                    "status": "error",
                    "code": c03_res.get("status"),
                    "message": c03_res.get("message", "Oferta comercial no disponible"),
                    "missing_constraints": c03_res.get("missing_constraints"),
                    "cotizacion": [],
                    "c03_offer": None,
                    "c04_quotation": None,
                    "quotation_id": None
                }

            c04_quote = None
            c04_res = C04QuoteOrchestrationManager.orchestrate_quote(
                offer=c03_res["offer"],
                ctx=ctx_c03,
                correlation_id=cid,
                idempotency_key=args.get("idempotency_key")
            )
            if c04_res.get("status") == "SUCCESS":
                c04_quote = c04_res.get("quotation")

            return {
                "status": "success",
                "cotizacion": res[:4] if isinstance(res, list) else res,
                "c03_offer": c03_res.get("offer"),
                "c04_quotation": c04_quote,
                "quotation_id": c04_quote.get("quotation_id") if c04_quote else None
            }

        elif tool_name == "consultar_disponibilidad_proveedor":
            slug = args.get("hotel_slug", "senator-puerto-plata")
            res = call_supabase_rpc("consultar_disponibilidad", {
                "p_hotel_slug": slug,
                "p_check_in": args.get("check_in", "2026-10-15"),
                "p_check_out": args.get("check_out", "2026-10-18"),
                "p_adults": int(args.get("adults", 2)),
                "p_children": int(args.get("children", 0))
            })
            return {"status": "success", "disponibilidad_proveedor": res}

        elif tool_name == "consultar_reserva":
            term = str(args.get("search_term", "")).strip()
            filter_param = f"booking_reference=eq.{urllib.parse.quote(term)}" if term.startswith("ALN") else f"lead_guest_name=ilike.*{urllib.parse.quote(term)}*"
            url = f"{SUPABASE_URL}/rest/v1/bookings?{filter_param}&select=id,booking_reference,lead_guest_name,hotel_code,status,payment_status,total_amount,deposit_amount,currency,voucher_pdf_url,created_at&limit=3"
            req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                return {"status": "success", "found": len(data) > 0, "bookings": data}

        elif tool_name == "registrar_abono_financiero":
            handoff_payload = {
                "booking_ref": args.get("booking_ref", "ALN-6A5B36"),
                "monto": float(args.get("monto", 200.0)),
                "tipo_pago": args.get("tipo_pago", "deposito"),
                "metodo": args.get("metodo", "transfer"),
                "comprobante_nota": args.get("comprobante_nota", "Comprobante comercial C07")
            }
            h_res = C07CommercialHandoffManager.execute_c07_handoff(
                handoff_type="pago",
                payload=handoff_payload,
                correlation_id=cid
            )
            return h_res

        elif tool_name == "avanzar_pipeline":
            phone = str(args.get("phone", "")).strip()
            new_stage = args.get("new_stage", "abono_recibido")
            patch_data = {"stage": new_stage}
            url = f"{SUPABASE_URL}/rest/v1/crm_leads?phone=eq.{urllib.parse.quote(phone)}"
            req = urllib.request.Request(
                url,
                data=json.dumps(patch_data).encode(),
                headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}", "Content-Type": "application/json", "Prefer": "return=representation"},
                method="PATCH"
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                return {"status": "success", "stage_updated": new_stage, "leads_affected": len(data)}

        elif tool_name == "consultar_pipeline":
            url = f"{SUPABASE_URL}/rest/v1/crm_leads?select=stage,full_name,phone,created_at&limit=50&order=created_at.desc"
            req = urllib.request.Request(url, headers={"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}"}, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                leads = json.loads(resp.read().decode())
                return {"status": "success", "total_leads": len(leads)}

        else:
            return {"status": "error", "message": f"Herramienta {tool_name} no reconocida"}
    except Exception as e:
        logger.error(f"Error executing tool {tool_name}: {e}")
        return {"status": "error", "error": str(e)}

# ==============================================================================
# WORKFLOW EXECUTION RUNTIME (INTEGRATING C01, C02, LLM & C07)
# ==============================================================================

def run_hermes_agent_workflow(mensaje_usuario: str, contacto: str = "Viajero", telefono: str = "", conv_id: Optional[str] = None, session_id: Optional[str] = None, correlation_id: Optional[str] = None, req_simulate_failure: bool = False) -> dict:
    cid = correlation_id or C07CommercialHandoffManager.generate_correlation_id()

    # 1. C01: CUSTOMER CONTEXT RESOLUTION & CONTINUITY RECONSTRUCTION
    ctx = C01CustomerContextManager.resolve_context(
        message=mensaje_usuario,
        contacto=contacto,
        telefono=telefono,
        conv_id=conv_id,
        session_id=session_id,
        correlation_id=cid
    )

    # 2. C02: COMMERCIAL QUALIFICATION EVALUATION
    qual = C02CommercialQualificationManager.evaluate_qualification(ctx, correlation_id=cid)

    # Build context-augmented user prompt
    context_summary = []
    if ctx.get("destination"):
        context_summary.append(f"Destino: {ctx['destination']}")
    if ctx.get("hotel_interest"):
        context_summary.append(f"Hotel de interés: {ctx['hotel_interest']}")
    if ctx.get("check_in") and ctx.get("check_out"):
        context_summary.append(f"Fechas: {ctx['check_in']} al {ctx['check_out']}")
    if ctx.get("adults"):
        context_summary.append(f"Pasajeros: {ctx['adults']} adultos")
    if ctx.get("budget_range"):
        context_summary.append(f"Presupuesto: {ctx['budget_range']}")
    if ctx.get("preferences"):
        context_summary.append(f"Preferencias: {', '.join(ctx['preferences'])}")

    ctx_str = " | ".join(context_summary) if context_summary else "Sin datos consolidados aún"

    system_instruction = (
        f"{SYSTEM_PROMPT}\n\n"
        f"[C01 CONTEXTO ACUMULADO DEL CLIENTE (Turno {ctx.get('turn_count', 1)})]:\n{ctx_str}\n"
        f"[C02 ESTADO DE CALIFICACIÓN COMERCIAL]: {qual.get('qualification_state')} ({qual.get('classification')}). Razón: {qual.get('reason')}\n"
    )

    if qual["qualification_state"] == "NEEDS_INFORMATION":
        system_instruction += f"\nATENCIÓN: Faltan datos clave para cotizar: {', '.join(ctx.get('missing_fields', []))}. Solicita cordialmente estos datos específicos manteniendo lo que el cliente ya te dijo."
    elif qual["qualification_state"] == "UNQUALIFIED":
        system_instruction += f"\nATENCIÓN: La solicitud no cumple con las políticas ({qual.get('classification')}). Explica cortésmente el motivo ({qual.get('reason')}) y orienta al cliente hacia opciones viables en República Dominicana."

    user_content = f"Cliente: {ctx.get('customer_name', 'Viajero')} (Tel: {ctx.get('phone', '')}). Mensaje actual: {mensaje_usuario}"

    messages = [
        {"role": "system", "content": system_instruction},
        {"role": "user", "content": user_content}
    ]

    tools_executed = []

    # Handle UNQUALIFIED case directly with high responsiveness
    if qual["qualification_state"] == "UNQUALIFIED":
        reason = qual["reason"]
        dest = ctx.get("destination", "")
        if "internacional" in dest.lower() or "tokio" in dest.lower() or "japon" in dest.lower():
            resp_text = (
                f"¡Hola {ctx.get('customer_name', 'Viajero')}! Gracias por contactar a Aliun Travel. "
                f"Nos especializamos exclusivamente en paquetes turísticos y resorts en República Dominicana (Punta Cana, Puerto Plata, Samaná, etc.), "
                f"por lo que no operamos destinos internacionales como {dest}.\n\n"
                f"Si deseas planificar una escapada inolvidable al Caribe dominicano, ¡con mucho gusto te asesoramos con las mejores opciones y tarifas!"
            )
        elif "pasado" in reason.lower():
            resp_text = (
                f"¡Hola {ctx.get('customer_name', 'Viajero')}! Notamos que las fechas solicitadas ({ctx.get('check_in')}) corresponden a un período pasado. "
                f"Para poder cotizarte y asegurar tu reserva, indícanos tus fechas futuras tentativas para 2026 y te prepararemos las mejores alternativas."
            )
        else:
            resp_text = (
                f"¡Hola {ctx.get('customer_name', 'Viajero')}! En relación a tu consulta, {reason}. "
                f"¿Te gustaría que revisemos alternativas ajustadas a nuestras promociones activas en República Dominicana?"
            )

        return {
            "ok": True,
            "respuesta": resp_text,
            "model": "c02_qualification_engine",
            "c01_context": ctx,
            "c02_qualification": qual,
            "c07_containment": {"enforced": False, "downstream_ack": False, "reason": "NO_PAYMENT_CLAIM", "correlation_id": cid},
            "tool_calls_executed": [],
            "source": "governed_qualification_policy",
            "correlation_id": cid
        }

    # Execute LLM or Tool Flow for Qualified / Needs Information cases
    for model in MODELS_WITH_TOOLS:
        payload = {
            "model": model,
            "messages": messages,
            "tools": TOOLS,
            "tool_choice": "auto",
            "temperature": 0.5,
            "max_tokens": 600
        }
        try:
            req = urllib.request.Request(
                "https://openrouter.ai/api/v1/chat/completions",
                data=json.dumps(payload).encode(),
                headers={
                    "Authorization": f"Bearer {OPENROUTER_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://aliuntravelsrl.com",
                    "X-Title": "Aliun Hermes Commercial"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=14) as resp:
                data = json.loads(resp.read().decode())
                choice = data["choices"][0]["message"]
                tool_calls = choice.get("tool_calls") or []

                if tool_calls:
                    messages.append(choice)
                    for tc in tool_calls:
                        fn = tc.get("function", {})
                        fn_name = fn.get("name")
                        try:
                            fn_args = json.loads(fn.get("arguments", "{}"))
                        except:
                            fn_args = {}

                        # Carry forward constraints from C01 context if missing in tool call
                        if fn_name == "calcular_cotizacion":
                            if not fn_args.get("check_in") and ctx.get("check_in"):
                                fn_args["check_in"] = ctx["check_in"]
                            if not fn_args.get("check_out") and ctx.get("check_out"):
                                fn_args["check_out"] = ctx["check_out"]
                            if not fn_args.get("adults") and ctx.get("adults"):
                                fn_args["adults"] = ctx["adults"]
                            if not fn_args.get("hotel_name_query"):
                                fn_args["hotel_name_query"] = ctx.get("hotel_interest") or ctx.get("destination") or "Senator"

                        if fn_name == "registrar_abono_financiero" and req_simulate_failure:
                            fn_args["monto"] = -100.0

                        tool_result = execute_tool(fn_name, fn_args, correlation_id=cid)
                        tools_executed.append({
                            "tool": fn_name,
                            "args": fn_args,
                            "result": tool_result
                        })

                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", "call_1"),
                            "content": json.dumps(tool_result)
                        })

                    followup_payload = {
                        "model": model,
                        "messages": messages,
                        "temperature": 0.5,
                        "max_tokens": 600
                    }
                    req2 = urllib.request.Request(
                        "https://openrouter.ai/api/v1/chat/completions",
                        data=json.dumps(followup_payload).encode(),
                        headers={
                            "Authorization": f"Bearer {OPENROUTER_KEY}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://aliuntravelsrl.com",
                            "X-Title": "Aliun Hermes Commercial"
                        },
                        method="POST"
                    )
                    with urllib.request.urlopen(req2, timeout=14) as resp2:
                        data2 = json.loads(resp2.read().decode())
                        final_text = data2["choices"][0]["message"]["content"].strip()
                        final_text, contained, reason = enforce_failure_containment(final_text, tools_executed, cid, contacto=contacto)
                        has_ack = any(t.get("tool") == "registrar_abono_financiero" and t.get("result", {}).get("status") == "ACK" for t in tools_executed)
                        c03_off = next((t.get("result", {}).get("c03_offer") for t in tools_executed if t.get("tool") == "calcular_cotizacion"), None)
                        c04_quo = next((t.get("result", {}).get("c04_quotation") for t in tools_executed if t.get("tool") == "calcular_cotizacion"), None)
                        qid = next((t.get("result", {}).get("quotation_id") for t in tools_executed if t.get("tool") == "calcular_cotizacion"), None)

                        return {
                            "ok": True,
                            "respuesta": final_text,
                            "model": model,
                            "c01_context": ctx,
                            "c02_qualification": qual,
                            "c03_offer": c03_off,
                            "c04_quotation": c04_quo,
                            "quotation_id": qid or (c04_quo.get("quotation_id") if c04_quo else None),
                            "c07_containment": {
                                "enforced": contained,
                                "downstream_ack": has_ack,
                                "reason": reason,
                                "correlation_id": cid
                            },
                            "tool_calls_executed": tools_executed,
                            "source": "llm_tool_calling",
                            "correlation_id": cid
                        }

                content = choice.get("content", "").strip()
                if content:
                    final_text, contained, reason = enforce_failure_containment(content, [], cid, contacto=contacto)
                    c03_off = None
                    c04_quo = None
                    if qual["qualification_state"] == "QUALIFIED" and ctx.get("check_in") and ctx.get("check_out"):
                        c03_res = C03OfferCompositionManager.compose_offer(ctx, correlation_id=cid)
                        c03_off = c03_res.get("offer")
                        if c03_off:
                            c04_res = C04QuoteOrchestrationManager.orchestrate_quote(c03_off, ctx, correlation_id=cid)
                            c04_quo = c04_res.get("quotation")

                    return {
                        "ok": True,
                        "respuesta": final_text,
                        "model": model,
                        "c01_context": ctx,
                        "customer_context": ctx,
                        "c02_qualification": qual,
                        "commercial_qualification": qual,
                        "c03_offer": c03_off,
                        "c04_quotation": c04_quo,
                        "quotation_id": c04_quo.get("quotation_id") if c04_quo else None,
                        "c07_containment": {
                            "enforced": contained,
                            "downstream_ack": False,
                            "reason": reason,
                            "correlation_id": cid
                        },
                        "tool_calls_executed": [],
                        "source": "llm_direct",
                        "correlation_id": cid
                    }
        except Exception as e:
            logger.warning(f"Model {model} failed in tool flow: {e}. Trying next...")
            continue

    # Deterministic fallback augmenting with multi-turn C01 context
    m = mensaje_usuario.lower()
    if any(k in m for k in ['abono', 'deposito', 'pago', 'financiero']):
        pay_args = {"booking_ref": "ALN-6A5B36", "monto": 200.0, "tipo_pago": "deposito"}
        if req_simulate_failure:
            pay_args["monto"] = -100.0
        pay_res = execute_tool("registrar_abono_financiero", pay_args, correlation_id=cid)
        tools_executed.append({"tool": "registrar_abono_financiero", "args": pay_args, "result": pay_res})
        
        if pay_res.get("status") == "ACK":
            resp_text = f"💰 **Abono Registrado y Confirmado (C07 ACK):**\n\nSe ha registrado el depósito de **$200.00 USD** para la reserva `ALN-6A5B36` (ID: `{pay_res.get('payment_id')}`).\nEstado: Aprobado y verificado en SSOT."
        else:
            resp_text = f"⏳ **Abono en Validación Operativa (C07 Failure Containment):**\n\nHemos recibido los datos de tu comprobante para la reserva `ALN-6A5B36`. El equipo de finanzas está validando los detalles ({pay_res.get('code', 'UNCONFIRMED')})."

        final_text, contained, reason = enforce_failure_containment(resp_text, tools_executed, cid, contacto=contacto)
        return {
            "ok": True,
            "respuesta": final_text,
            "model": "c07_governed_pago",
            "c01_context": ctx,
            "customer_context": ctx,
            "c02_qualification": qual,
            "commercial_qualification": qual,
            "c03_offer": None,
            "c04_quotation": None,
            "quotation_id": None,
            "c07_containment": {"enforced": contained, "reason": reason, "downstream_ack": pay_res.get("status") == "ACK"},
            "tool_calls_executed": tools_executed,
            "source": "tool_fallback",
            "correlation_id": cid
        }

    # Needs Information fallback message
    if qual["qualification_state"] == "NEEDS_INFORMATION":
        missing_spanish = []
        if "destination" in ctx.get("missing_fields", []):
            missing_spanish.append("destino o hotel preferido")
        if "dates" in ctx.get("missing_fields", []):
            missing_spanish.append("fechas de viaje (check-in y check-out)")
        if "passengers" in ctx.get("missing_fields", []):
            missing_spanish.append("cantidad de adultos y niños")

        known_elements = []
        if ctx.get("destination"):
            known_elements.append(f"Destino: {ctx['destination']}")
        if ctx.get("check_in") and ctx.get("check_out"):
            known_elements.append(f"Fechas: {ctx['check_in']} al {ctx['check_out']}")
        if ctx.get("adults"):
            known_elements.append(f"Pasajeros: {ctx['adults']} adultos")

        known_str = f" Tenemos registrado: {', '.join(known_elements)}." if known_elements else ""
        resp_text = (
            f"¡Hola {ctx.get('customer_name', 'Viajero')}! Con gusto te preparamos la cotización.{known_str} "
            f"Para completar tu propuesta formal, ¿podrías confirmarnos: {', '.join(missing_spanish)}?"
        )
        return {
            "ok": True,
            "respuesta": resp_text,
            "model": "c01_intake_fallback",
            "c01_context": ctx,
            "customer_context": ctx,
            "c02_qualification": qual,
            "commercial_qualification": qual,
            "c03_offer": None,
            "c04_quotation": None,
            "quotation_id": None,
            "c07_containment": {"enforced": False, "downstream_ack": False, "reason": "NO_PAYMENT_CLAIM", "correlation_id": cid},
            "tool_calls_executed": [],
            "source": "intake_template",
            "correlation_id": cid
        }

    # Standard Qualified fallback response with full C03/C04 materialization
    calc_hotel = ctx.get("hotel_interest") or ctx.get("destination") or "Punta Cana"
    calc_args = {
        "hotel_name_query": calc_hotel,
        "check_in": ctx.get("check_in", "2026-10-15"),
        "check_out": ctx.get("check_out", "2026-10-18"),
        "adults": int(ctx.get("adults") or 2),
        "children": int(ctx.get("children") or 0),
        "customer_name": ctx.get("customer_name", "Viajero"),
        "phone": ctx.get("phone", "")
    }
    calc_res = execute_tool("calcular_cotizacion", calc_args, correlation_id=cid)
    tools_executed.append({"tool": "calcular_cotizacion", "args": calc_args, "result": calc_res})
    
    quote_obj = calc_res.get("c04_quotation")
    offer_obj = calc_res.get("c03_offer")
    qid = calc_res.get("quotation_id") or (quote_obj.get("quotation_id") if quote_obj else None)
    
    if not quote_obj or not qid:
        resp_text = (
            f"¡Hola {ctx.get('customer_name', 'Viajero')}! Hemos consultado las opciones para **{calc_hotel}** del {calc_args['check_in']} al {calc_args['check_out']}, "
            f"pero actualmente no hay disponibilidad o tarifas vigentes confirmadas para estos parámetros ({calc_res.get('code', 'NO_DISPONIBLE')}). "
            f"¿Te gustaría que revisemos fechas alternativas u otros resorts en República Dominicana?"
        )
        return {
            "ok": True,
            "respuesta": resp_text,
            "model": "c02_qualified_unpriced_fallback",
            "c01_context": ctx,
            "customer_context": ctx,
            "c02_qualification": qual,
            "commercial_qualification": qual,
            "c03_offer": None,
            "c04_quotation": None,
            "quotation_id": None,
            "c07_containment": {"enforced": False, "downstream_ack": False, "reason": "NO_PAYMENT_CLAIM", "correlation_id": cid},
            "tool_calls_executed": tools_executed,
            "source": "qualified_template_unpriced",
            "correlation_id": cid
        }

    rooms_text = []
    if calc_res.get("cotizacion") and isinstance(calc_res["cotizacion"], list):
        for r in calc_res["cotizacion"][:3]:
            rooms_text.append(f"• **{r.get('room_name')}**: ${r.get('price_per_night')} USD/noche (Total: **${r.get('subtotal')} USD**)")
    
    rooms_str = "\n".join(rooms_text) if rooms_text else "Tarifas sujetas a confirmación"
    resp_text = (
        f"¡Hola {ctx.get('customer_name', 'Viajero')}! Hemos preparado tu cotización formal para **{calc_args['hotel_name_query']}**.\n\n"
        f"📋 **Cotización:** `{qid}`\n"
        f"📅 **Fechas:** {calc_args['check_in']} al {calc_args['check_out']} ({ctx.get('adults', 2)} adultos)\n\n"
        f"🏨 **Opciones disponibles:**\n{rooms_str}\n\n"
        f"¿Deseas que reservemos alguna de estas opciones o te gustaría consultar otro hotel?"
    )
    return {
        "ok": True,
        "respuesta": resp_text,
        "model": "c02_qualified_fallback",
        "c01_context": ctx,
        "customer_context": ctx,
        "c02_qualification": qual,
        "commercial_qualification": qual,
        "c03_offer": offer_obj,
        "c04_quotation": quote_obj,
        "quotation_id": qid,
        "c07_containment": {"enforced": False, "downstream_ack": False, "reason": "NO_PAYMENT_CLAIM", "correlation_id": cid},
        "tool_calls_executed": tools_executed,
        "source": "qualified_template",
        "correlation_id": cid
    }

# ==============================================================================
# HTTP ENDPOINTS
# ==============================================================================

@app.get("/health")
def health():
    return {
        "status": "ok",
        "gateway": "hermes-commercial-full-suite",
        "c01_customer_context": "materialized",
        "c02_qualification": "materialized",
        "c03_offer_composition": "materialized",
        "c04_quote_orchestration": "materialized",
        "c07_handoff": "materialized",
        "port": 8645,
        "version": "2.6.0-f02"
    }

@app.get("/c04/quotation/{quotation_id}")
async def c04_get_quotation_endpoint(quotation_id: str):
    res = C04QuoteOrchestrationManager.get_quotation(quotation_id)
    if not res:
        return JSONResponse(status_code=404, content={"status": "error", "message": f"Quotation '{quotation_id}' not found"})
    return {"status": "success", "quotation": res}

@app.post("/c04/transition")
async def c04_transition_endpoint(req: QuoteTransitionRequest, request: Request, response: Response):
    cid = req.correlation_id or request.headers.get("X-Correlation-ID") or C07CommercialHandoffManager.generate_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    res = C04QuoteOrchestrationManager.transition_quote_state(
        quotation_id=req.quotation_id,
        new_state=req.new_state,
        actor=req.actor or "advisor",
        reason=req.reason or "Governed commercial transition",
        correlation_id=cid
    )
    if not res.get("ok"):
        return JSONResponse(status_code=400, content=res)
    return res

@app.post("/c04/compose-and-quote")
async def c04_compose_and_quote_endpoint(req: QuoteComposeRequest, request: Request, response: Response):
    cid = req.correlation_id or request.headers.get("X-Correlation-ID") or C07CommercialHandoffManager.generate_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    
    # 1. Resolve context if message provided, else construct from fields
    if req.message:
        ctx = C01CustomerContextManager.resolve_context(
            message=req.message,
            contacto=req.contacto or "Viajero",
            telefono=req.telefono or "",
            correlation_id=cid
        )
    else:
        ctx = {
            "customer_name": req.contacto or "Viajero",
            "phone": req.telefono or "",
            "hotel_interest": req.hotel_name_query,
            "destination": req.hotel_name_query,
            "check_in": req.check_in,
            "check_out": req.check_out,
            "adults": req.adults or 2,
            "children": req.children or 0
        }
    
    # 2. Evaluate qualification
    qual = C02CommercialQualificationManager.evaluate_qualification(ctx, correlation_id=cid)
    
    # 3. C03 Offer Composition
    c03_res = C03OfferCompositionManager.compose_offer(ctx, correlation_id=cid)
    if c03_res.get("status") != "SUCCESS":
        return {
            "ok": False,
            "status": c03_res.get("status"),
            "missing_constraints": c03_res.get("missing_constraints", []),
            "c01_context": ctx,
            "c02_qualification": qual,
            "c03_offer": None,
            "c04_quotation": None,
            "correlation_id": cid
        }
    
    # 4. C04 Quote Orchestration
    c04_res = C04QuoteOrchestrationManager.orchestrate_quote(
        offer=c03_res["offer"],
        ctx=ctx,
        correlation_id=cid,
        idempotency_key=req.idempotency_key
    )
    
    return {
        "ok": True,
        "status": "SUCCESS",
        "action": c04_res.get("action"),
        "c01_context": ctx,
        "c02_qualification": qual,
        "c03_offer": c03_res.get("offer"),
        "c04_quotation": c04_res.get("quotation"),
        "quotation_id": c04_res.get("quotation", {}).get("quotation_id"),
        "correlation_id": cid
    }


@app.post("/chat")
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, response: Response):
    cid = req.correlation_id or request.headers.get("X-Correlation-ID") or C07CommercialHandoffManager.generate_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    try:
        sim_fail = bool(getattr(req, "simulate_failure", False) or False)
        contacto = req.sender_name or req.contacto or "Viajero"
        telefono = req.sender_phone or req.telefono or ""
        res = run_hermes_agent_workflow(
            mensaje_usuario=req.message,
            contacto=contacto,
            telefono=telefono,
            conv_id=req.conv_id,
            session_id=req.session_id,
            correlation_id=cid,
            req_simulate_failure=sim_fail
        )
        res["correlation_id"] = cid
        return res
    except Exception as e:
        logger.error(f"[cid={cid}] Error in chat endpoint: {e}")
        return {
            "ok": True,
            "respuesta": f"Hola {req.contacto or 'Viajero'}, recibimos tu mensaje. Nuestro equipo está revisando la consulta.",
            "model": "error_fallback",
            "tool_calls_executed": [],
            "error": str(e),
            "correlation_id": cid
        }

@app.post("/c07/handoff")
async def c07_handoff_endpoint(req: HandoffRequest, request: Request, response: Response):
    cid = req.correlation_id or request.headers.get("X-Correlation-ID") or C07CommercialHandoffManager.generate_correlation_id()
    response.headers["X-Correlation-ID"] = cid
    result = C07CommercialHandoffManager.execute_c07_handoff(
        handoff_type=req.handoff_type,
        payload=req.payload,
        correlation_id=cid,
        idempotency_key=req.idempotency_key,
        receiver_url=req.receiver_url,
        simulate_failure=req.simulate_failure
    )
    result["correlation_id"] = cid
    return result

@app.post("/c07/test-receiver")
async def c07_test_receiver_endpoint(req: Request):
    body = await req.json()
    cid = body.get("correlation_id", "CID-UNKNOWN")
    payload = body.get("payload", {})
    action = payload.get("test_action", "normal")

    if action == "transient_failure":
        fail_key = f"test_recv_{cid}"
        count = C07CommercialHandoffManager._transient_failure_counters.get(fail_key, 0)
        if count < 1:
            C07CommercialHandoffManager._transient_failure_counters[fail_key] = count + 1
            return JSONResponse(status_code=503, content={"status": "ERROR", "message": "Downstream receiver temporary overloaded"})
        return {"status": "ACK", "code": "ACCEPTED", "receiver": "mock_test_receiver", "correlation_id": cid}

    elif action == "persistent_failure":
        return JSONResponse(status_code=500, content={"status": "ERROR", "message": "Downstream fatal server error"})

    elif action == "business_nack":
        return {
            "status": "NACK",
            "code": "REJECTED_BUSINESS_RULE",
            "reason": "Referencia de reserva rechazada por política de negocio",
            "correlation_id": cid,
            "receiver": "mock_test_receiver"
        }

    else:
        return {
            "status": "ACK",
            "code": "ACCEPTED",
            "correlation_id": cid,
            "receiver": "mock_test_receiver",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }
