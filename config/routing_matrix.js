/**
 * routing_matrix.js — Matriz de ruteo comercial Hermes Commercial
 * Heredado de atlas-sales-v2/config/routing_matrix.js
 * Adaptado: sin Paperclip, sin Kommo, routing por intención comercial
 * Fecha: 29 MAY 2026
 */

export const DEPARTMENTS = {
  1: {
    id: '01_ventas',
    name: 'Ventas',
    description: 'Conexión, descubrimiento, construcción de valor, cotización',
    model: 'google/gemini-2.0-flash-lite-001',
    keywords: ['paquete', 'cotización', 'viaje', 'hotel', 'all-inclusive', 'reserva', 'precio', 'destino', 'punta cana', 'bayahibe', 'samana', 'bavaro'],
    stageTriggers: ['nuevo_contacto', 'conversacion_inicial', 'descubrimiento', 'construccion_valor'],
  },
  2: {
    id: '02_disponibilidad',
    name: 'Disponibilidad',
    description: 'Consulta de fechas, habitaciones, cupos, temporadas',
    model: 'qwen/qwen3.5-flash-02-23',
    keywords: ['disponibilidad', 'fechas', 'habitaciones', 'cupo', 'temporada', 'ocupado', 'libre', 'quedan'],
    stageTriggers: ['cotizacion_enviada'],
  },
  3: {
    id: '03_finanzas',
    name: 'Finanzas',
    description: 'Pagos, depósitos, comprobantes, facturación',
    model: 'qwen/qwen3.6-flash',
    keywords: ['pago', 'depósito', 'transferencia', 'comprobante', 'factura', 'recibo', 'abono', 'banco', 'tarjeta'],
    stageTriggers: ['cierre', 'en_pagos'],
    hasAttachment: true,
  },
  4: {
    id: '04_seguimiento',
    name: 'Seguimiento',
    description: 'Follow-ups T+2h/24h/48h, reactivación de leads fríos',
    model: 'mistralai/ministral-8b-2512',
    keywords: ['seguro', 'confirmar', 'recordar', 'volver', 'pendiente', 'todavía'],
    stageTriggers: ['objecion_en_manejo'],
    isFollowup: true,
  },
  5: {
    id: '05_soporte',
    name: 'Soporte',
    description: 'Cancelaciones, cambios, vouchers, problemas',
    model: 'google/gemini-2.0-flash-lite-001',
    keywords: ['cancelar', 'cambiar', 'modificar', 'voucher', 'problema', 'queja', 'reclamo', 'no funciona'],
    stageTriggers: ['en_fulfillment', 'cerrado'],
  },
  6: {
    id: '06_sales_escalation',
    name: 'Escalamiento',
    description: 'Mayoristas, grupos grandes, excepciones de precio, Director',
    model: 'google/gemini-2.0-flash-001',
    keywords: ['mayorista', 'agencia', 'grupo grande', 'descuento especial', 'director', 'B2B', 'corporativo', 'convención'],
    stageTriggers: [],
    alwaysRoute: true,
  },
};

/**
 * Sugiere departamento basado en contenido del mensaje y contexto del lead
 */
export function suggestDepartment(message, leadContext = {}) {
  const text = (message || '').toLowerCase();
  const stage = leadContext.stage || '';

  // Prioridad 1: Escalamiento (siempre primero)
  const esc = DEPARTMENTS[6];
  if (esc.keywords.some(kw => text.includes(kw))) return esc;

  // Prioridad 2: Finanzas (comprobante o adjunto)
  const fin = DEPARTMENTS[3];
  if (fin.keywords.some(kw => text.includes(kw)) || leadContext.hasAttachment) return fin;

  // Prioridad 3: Seguimiento (respuesta a follow-up)
  const seg = DEPARTMENTS[4];
  if (leadContext.isFollowupResponse) return seg;

  // Prioridad 4: Disponibilidad (post-cotización)
  const disp = DEPARTMENTS[2];
  if (disp.keywords.some(kw => text.includes(kw)) && disp.stageTriggers.includes(stage)) return disp;

  // Prioridad 5: Soporte (post-venta)
  const sop = DEPARTMENTS[5];
  if (sop.keywords.some(kw => text.includes(kw)) || sop.stageTriggers.includes(stage)) return sop;

  // Default: Ventas
  return DEPARTMENTS[1];
}

/**
 * Sugiere tools según departamento
 */
export function suggestTools(departmentId) {
  const toolMap = {
    '01_ventas': ['buscar_hoteles', 'consultar_disponibilidad', 'calcular_cotizacion', 'obtener_galeria_hotel', 'registrar_lead'],
    '02_disponibilidad': ['consultar_disponibilidad', 'calcular_precio_paquete', 'buscar_ofertas_marketing'],
    '03_finanzas': ['validar_comprobante', 'registrar_deposito'],
    '04_seguimiento': ['registrar_actividad', 'avanzar_pipeline', 'consultar_pipeline'],
    '05_soporte': ['consultar_disponibilidad', 'registrar_actividad'],
    '06_sales_escalation': ['calcular_cotizacion', 'calcular_precio_paquete', 'registrar_lead'],
  };
  return toolMap[departmentId] || [];
}

/**
 * Genera contexto de routing para el orquestador
 */
export function getRoutingMatrixContext() {
  return Object.values(DEPARTMENTS).map(d => ({
    id: d.id,
    name: d.name,
    model: d.model,
    keywords: d.keywords,
  }));
}
