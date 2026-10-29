const KEY = "sgrs.token";
const safe = (fn, d = null) => { try { return fn(); } catch { return d; } };

export const auth = {
  get token() { return safe(() => localStorage.getItem(KEY)); },
  set(t) { safe(() => localStorage.setItem(KEY, t)); },
  clear() { safe(() => localStorage.removeItem(KEY)); },
};

const MESSAGES = {
  TICKET_UNAVAILABLE: "Alguien tomó una de esas boletas. Elige otras.",
  SALES_CLOSED: "Las ventas de esta rifa ya cerraron.",
  AMOUNT_MISMATCH: "El monto no coincide con el valor de las boletas.",
  PROOF_REQUIRED: "Indica el número de transacción o adjunta el comprobante.",
  DUPLICATE_EXTERNAL_REF: "Ese número de transacción ya fue reportado.",
  DUPLICATE_PROOF: "Ese comprobante ya respalda otro pago de esta rifa.",
  PROOF_NOT_FOUND: "No se encontró el comprobante. Súbelo de nuevo.",
  OTP_INVALID: "Código incorrecto o vencido.",
  OTP_LOCKED: "Demasiados intentos. Solicita un código nuevo en unos minutos.",
  OTP_SEND_FAILED: "No pudimos enviar el código por WhatsApp. Intenta de nuevo en unos minutos.",
  OTP_TOO_SOON: "Espera un minuto antes de pedir otro código.",
  PHONE_INVALID: "Número inválido. Usa el formato +573001234567.",
  UNSUPPORTED_TYPE: "Formato no permitido. Usa PNG, JPG, WebP o PDF.",
  FILE_TOO_LARGE: "El archivo supera 5 MB.",
  FORBIDDEN: "No tienes permiso para esta acción.",
  INVALID_STATE: "La operación ya no es válida (el estado cambió). Actualiza la página.",
  EXPIRED: "La reserva expiró.",
  BEFORE_CLOSING_DATE: "Aún no llega la fecha de cierre; la rifa se cerrará sola cuando corresponda.",
  PENDING_TX_REMAIN: "Resuelve todas las transacciones pendientes antes de sortear.",
  NO_SOLD_TICKETS: "No hay boletas vendidas para sortear.",
  EXTERNAL_RESULT_REQUIRED: "Ingresa el número oficial y el enlace de comprobación.",
  NUMBER_OUT_OF_RANGE: "El número está fuera del rango de la rifa.",
};

export class ApiError extends Error {
  constructor(status, code, extra) {
    super(MESSAGES[code] || (status === 0 ? "Sin conexión con el servidor." : `Error ${status}${code ? " (" + code + ")" : ""}`));
    this.status = status; this.code = code; this.extra = extra || {};
  }
}

async function req(method, path, { json, body, headers = {} } = {}) {
  const h = { ...headers };
  if (auth.token) h.Authorization = "Bearer " + auth.token;
  if (json !== undefined) h["Content-Type"] = "application/json";
  let res;
  try {
    res = await fetch("/api/v1" + path, { method, headers: h, body: json !== undefined ? JSON.stringify(json) : body });
  } catch { throw new ApiError(0); }
  if (res.status === 401 && auth.token && !path.startsWith("/auth/")) {
    auth.clear(); window.dispatchEvent(new Event("auth:expired"));
  }
  if (!res.ok) {
    let d = {};
    try { d = (await res.json()).detail || {}; } catch { /* sin cuerpo */ }
    const code = typeof d === "object" && !Array.isArray(d) ? d.code : Array.isArray(d) ? "VALIDATION" : undefined;
    throw new ApiError(res.status, code, d);
  }
  return res;
}

const j = async (p) => (await p).json();
export const api = {
  get: (p) => j(req("GET", p)),
  post: (p, json, headers) => j(req("POST", p, { json: json ?? {}, headers })),
  putBlob: (p, blob) => j(req("PUT", p, { body: blob })),
  blob: async (p) => (await req("GET", p)).blob(),
};
