# ROUTING.md — Matriz de Ruteo Comercial
## Hermes Commercial · Aliun Travel SRL

---

## 6 Departamentos Comerciales

| ID | Departamento | Keywords de activación | Sub-agente | Modelo |
|----|-------------|------------------------|------------|--------|
| 01 | VENTAS | paquete, cotización, viaje, hotel, all-inclusive, reserva | vendedor | gemini-2.0-flash-lite |
| 02 | DISPONIBILIDAD | disponibilidad, fechas, habitaciones, cupo, temporada | cotizador | qwen3.5-flash |
| 03 | FINANZAS | pago, depósito, transferencia, comprobante, factura, recibo | finanzas | qwen3.6-flash |
| 04 | SEGUIMIENTO | seguimiento, confirmar, recordar, volver, pendiente | qa-followup | ministral-8b |
| 05 | SOPORTE | cancelar, cambiar, modificar, voucher, problema, queja | vendedor | gemini-2.0-flash-lite |
| 06 | ESCALAMIENTO | mayorista, B2B, grupo grande, descuento especial, director | orquestador | gemini-2.0-flash |

---

## Lógica de ruteo

```javascript
function route(message, context) {
  const text = message.toLowerCase();
  const lead = context.lead;

  // Prioridad 1: Escalamiento (siempre primero)
  if (matchKeywords(text, ESCALAMIENTO.keywords)) return '06_sales_escalation';

  // Prioridad 2: Finanzas (si hay comprobante o mención de pago)
  if (matchKeywords(text, FINANZAS.keywords) || hasAttachment(message)) return '03_finanzas';

  // Prioridad 3: Seguimiento (si es respuesta a follow-up previo)
  if (lead.last_followup && isFollowupResponse(text)) return '04_seguimiento';

  // Prioridad 4: Disponibilidad (si ya cotizó y pide fechas/cupo)
  if (lead.stage >= 'cotizacion_enviada' && matchKeywords(text, DISPONIBILIDAD.keywords))
    return '02_disponibilidad';

  // Prioridad 5: Soporte (post-venta o problema)
  if (lead.stage >= 'en_fulfillment' || matchKeywords(text, SOPORTE.keywords))
    return '05_soporte';

  // Default: Ventas
  return '01_ventas';
}
```

---

## Escalamiento al Director

Condiciones que activan escalamiento inmediato:
- **Grupo 3+ habitaciones** → flujo preferencial
- **Mayorista/B2B detectado** → cuenta estratégica
- **Descuento >15%** → requiere autorización
- **Fuerza mayor** (huracán, overbooking, crisis) → Director decide
- **Lead >48h sin seguimiento** → alerta al sistema

Formato de escalamiento:
```
🚨 ESCALAMIENTO
Tipo: [grupo|B2B|descuento|fuerza_mayor]
Lead: [ID]
Contexto: [resumen 2 líneas]
Acción propuesta: [1 línea]
Aprobación: [✅/❌]
```

---

*Hermes Commercial · Aliun Travel SRL · 29 MAY 2026*
