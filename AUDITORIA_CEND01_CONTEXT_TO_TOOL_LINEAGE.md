# AUDITORÍA FÍSICA Y DE CÓDIGO: CEND-01 CONTEXT-TO-TOOL LINEAGE (HERMES COMMERCIAL)
**Código Canónico:** `AUDIT-CEND01-LINEAGE-HERMES-v1`  
**Fecha de Certificación Física:** 09 de Septiembre de 2026 (Local Time)  
**Host Auditado:** VPS2 (`srv1587803.hstgr.cloud` / IP: `2.24.198.231`)  
**Archivo Fuente Desplegado:** `/docker/hermes-agent-dpkf/data/gateway.py` (555 líneas)  
**Proceso Activo:** `PID 433` (`uvicorn gateway:app --host 0.0.0.0 --port 8645`)  
**Metodología:** Inspección estricta de código desplegado, volcado de scripts y telemetría de ejecución.  
**Estado:** ✅ CERTIFICADO EN PRODUCCIÓN (READ-ONLY EVIDENCE)

---

## 1. RESUMEN EJECUTIVO

Se completó el descenso de auditoría física y de código sobre la frontera **`CONTEXT-TO-TOOL LINEAGE`** en Hermes Commercial (VPS2), resolviendo de manera definitiva las contradicciones entre documentación y runtime.

---

## 2. MODELO EFECTIVO Y ENRUTAMIENTO DE INFERENCIA

| Parámetro | Valor Observado en Runtime | Origen Físico en Código |
|---|---|---|
| **Modelo Primario Activo** | `qwen/qwen-2.5-72b-instruct` | Hardcoded en array `MODELS_WITH_TOOLS` (Línea 42 de `gateway.py`). |
| **Modelos Fallback** | `nvidia/nemotron-3-super-120b-a12b:free`<br>`nex-agi/nex-n2.5-pro:free` | Hardcoded en array `MODELS_WITH_TOOLS` (Líneas 43-44). |
| **Proveedor** | OpenRouter API (`https://openrouter.ai/api/v1/chat/completions`) | Llamada HTTP POST en línea 344 de `gateway.py`. |
| **Resolución de Contradicción** | `qwen/qwen-2.5-72b-instruct` (Gateway :8645)<br>`nemotron-3` (CLI daemon stock :4860) | Son dos procesos independientes dentro del contenedor. El tráfico real de clientes por Chatwoot/n8n pasa exclusivamente por `gateway.py` (PID 433). |

---

## 3. CADENA REAL DE DECISIÓN Y FUNCTION CALLING

$$\text{DEMANDA CHAT} \xrightarrow{\text{n8n}} \text{gateway.py (:8645)} \xrightarrow{\text{OpenRouter}} \text{qwen-2.5-72b} \xrightarrow{\text{Tool Call}} \text{execute\_tool()} \xrightarrow{\text{RPC}} \text{Supabase} \xrightarrow{\text{Sintetizado}} \text{Chatwoot}$$

1. **Inexistencia de Capas Intermedias en Runtime:**
   * **¿Existe Capability Resolver?** **NO OBSERVADO / NO PRESENTE EN RUNTIME**.
   * **¿Existe Intent Classification intermedia?** **NO**.
   * **¿Existen Sub-agentes Swarm independientes en el flujo?** **NO OBSERVADO**.
   * **Mecanismo Real:** OpenRouter recibe las 7 herramientas en el payload y el LLM decide directamente mediante Function Calling nativo (`tool_choice: "auto"`).

---

## 4. ORIGEN DE ARGUMENTOS Y DIAGNÓSTICO DEL AÑO 2023

### Caso de Prueba Real:
* **Entrada:** *"Quiero cotizar 2 adultos en Occidental Punta Cana del 18 al 20 de septiembre"*
* **Tool Call emitido por LLM:** `calcular_cotizacion`
* **Argumentos generados:**
  * `hotel_name_query`: `"Occidental Punta Cana"` (extraído del mensaje).
  * `adults`: `2` (extraído del mensaje).
  * `check_in`: `"2023-09-18"` $\leftarrow$ **Inferencia por defecto del LLM**.
  * `check_out`: `"2023-09-20"` $\leftarrow$ **Inferencia por defecto del LLM**.

### Causa Raíz de Código:
1. En `gateway.py`, `SYSTEM_PROMPT` (Líneas 159-172) y `user_content` (Línea 325) **no inyectan la fecha actual ni el año**.
2. Al no recibir la fecha del sistema, `qwen/qwen-2.5-72b-instruct` infiere por defecto el año de su corte de entrenamiento (**2023**).
3. Al consultar la base de datos de tarifas para 2023, la RPC `calcular_cotizacion` retorna `cotizacion: []`, provocando que el modelo concluya falsamente: *"Veo que no hay disponibilidad para las fechas solicitadas"*.

---

## 5. ESTADO DEL CONTEXTO Y PERSISTENCIA (STATELESS)

* **En `gateway.py`:** La función `run_hermes_agent_workflow()` (Líneas 324-329) solo recibe `mensaje_usuario`, `contacto` y `telefono`. **No consulta `conversation_messages` ni turnos previos**. Cada invocación es completamente stateless.
* **En Supabase:** n8n intenta registrar la sesión vía RPC `canal_recibir_mensaje`, pero actualmente experimenta fallo por la restricción `direction NOT NULL` en `conversation_messages`.

---

## 6. TRAZABILIDAD Y REGISTRO EN LOGGER (`logs_operativos`)

1. **`GATEWAY_CHAT_PROCESADO` (Línea 465):**
   * Registra: `conv_id`, `tools_count` y `model`.
   * El campo `model` representa el **modelo que efectivamente respondió en OpenRouter** (`qwen/qwen-2.5-72b-instruct`).
2. **`HERMES_TOOL_EXECUTED` (Línea 380):**
   * Registra: `tool` y `args`.
   * No registra `model` ni `conv_id`; la correlación es temporal.

---

## 7. PRÓXIMA FRONTERA OPERATIVA

**`PROMPT-TEMPORAL-INJECTION & CONVERSATION BUFFER`**
* Inyectar `datetime.utcnow()` en el `SYSTEM_PROMPT` de `gateway.py` para asegurar que el LLM infiera `2026` en cotizaciones sin año explícito.
* Diseñar buffer multi-turno para retener contexto conversacional entre mensajes consecutivos.
