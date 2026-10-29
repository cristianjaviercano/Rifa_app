import { h } from "./dom.js";

// BORRADOR: texto base redactado sin revisión jurídica. Debe revisarlo un abogado (rifas y juegos de suerte
// y azar, crowdfunding y protección de datos personales) antes de invitar a usuarios externos.
// Al cambiarlo, actualiza TERMS_VERSION en app/legal.py para pedir una nueva aceptación.
const BORRADOR = "Borrador sin revisión jurídica. Los datos entre corchetes deben completarse antes de publicar.";

const TERMINOS = [
  ["1. Qué es este servicio", [
    "Rifa App es una herramienta de control para organizar rifas y campañas: registra números, reservas, comprobantes de pago, el cierre de ventas y el sorteo.",
    "La plataforma no procesa pagos, no recibe ni custodia dinero y no entrega premios. Los pagos se hacen directamente al organizador, que los valida con su propia cuenta.",
  ]],
  ["2. Responsabilidad del organizador", [
    "Quien crea una rifa es el único responsable de que sea legal: debe contar con las autorizaciones, permisos y registros que exija la normativa aplicable a rifas y juegos de suerte y azar, y de cumplir sus obligaciones tributarias.",
    "El organizador responde por recibir los pagos, verificar los comprobantes, realizar el sorteo conforme a lo que publicó y entregar el premio o la recompensa prometidos.",
  ]],
  ["3. Participantes", [
    "Al reportar un pago declaras que es real y que el comprobante es auténtico. Las boletas se reservan por un tiempo limitado mientras el organizador verifica el pago; si no se aprueba, se liberan.",
    "El resultado del sorteo se publica en la rifa. En el método externo, el organizador debe indicar la fuente pública que lo respalda.",
  ]],
  ["4. Uso aceptable", [
    "Está prohibido subir comprobantes falsos o ajenos, suplantar a otra persona, crear rifas engañosas o ilegales, intentar acceder a cuentas ajenas o sobrecargar el servicio. Podemos suspender cuentas y retirar contenido que incumpla estas reglas.",
  ]],
  ["5. Fase de pruebas (beta)", [
    "Mientras el servicio esté en beta, los pagos son ficticios, no se debe enviar dinero real y los datos pueden borrarse sin previo aviso. El servicio se ofrece sin garantías de disponibilidad.",
  ]],
  ["6. Limitación de responsabilidad", [
    "En la medida que permita la ley, la plataforma no responde por incumplimientos del organizador, por pagos hechos fuera de ella ni por premios no entregados. Cualquier reclamación por un pago o un premio debe dirigirse al organizador.",
  ]],
  ["7. Cambios y contacto", [
    "Podemos actualizar estos términos; si el cambio es relevante te pediremos aceptarlos de nuevo. Ley aplicable y jurisdicción: [LEY Y CIUDAD]. Responsable: [NOMBRE O RAZÓN SOCIAL]. Contacto: [CORREO DE CONTACTO].",
  ]],
];

const PRIVACIDAD = [
  ["1. Responsable", ["[NOMBRE O RAZÓN SOCIAL], [DOMICILIO]. Contacto para asuntos de datos personales: [CORREO DE CONTACTO]."]],
  ["2. Qué datos tratamos", [
    "Número de celular verificado, nombre que indiques, rifas que creas o en las que participas, comprobantes de pago e imágenes que subas, la aceptación de estos textos (fecha y versión) y registros técnicos de seguridad (por ejemplo dirección IP y referencia de cada petición, sin contenido).",
  ]],
  ["3. Para qué los usamos", [
    "Verificar tu identidad, permitir reservas y pagos, que el organizador valide tu pago y te contacte, enviarte avisos sobre tus compras y sorteos, prevenir fraude y abuso, y mantener la seguridad y el funcionamiento del servicio.",
  ]],
  ["4. Quién ve tus datos", [
    "El organizador de una rifa ve el nombre, el celular y los comprobantes de quienes le reportan pagos. Los demás participantes ven únicamente el estado de los números, no tus datos.",
    "Usamos proveedores para operar el servicio: alojamiento (Vercel), base de datos (Neon) y, si se activa, mensajería (WhatsApp/Meta) y monitoreo de errores (Sentry). Estos pueden tratar datos fuera de tu país.",
  ]],
  ["5. Conservación", ["Conservamos los datos mientras tengas cuenta o la rifa esté vigente y, después, por [PLAZO] para atender obligaciones legales y reclamaciones."]],
  ["6. Tus derechos", [
    "Puedes conocer, actualizar, rectificar y solicitar la supresión de tus datos, y revocar tu autorización, conforme a la normativa de protección de datos aplicable (en Colombia, la Ley 1581 de 2012). Escríbenos a [CORREO DE CONTACTO] indicando tu celular registrado.",
  ]],
  ["7. Seguridad y menores", [
    "Aplicamos cifrado en tránsito, control de acceso y registros de auditoría; ningún sistema es infalible. El servicio es solo para mayores de edad.",
  ]],
];

function page(title, sections, id) {
  return h("article", { class: "stack", id }, h("h1", null, title),
    h("p", { class: "chip warn" }, BORRADOR),
    sections.map(([head, paras]) => h("section", { class: "card" }, h("h2", null, head), paras.map((p) => h("p", null, p)))),
    h("p", { class: "muted" }, h("a", { href: "#/" }, "← Volver al inicio")));
}

export const terminosView = async () => page("Términos y condiciones de uso", TERMINOS, "terms-page");
export const privacidadView = async () => page("Política de privacidad", PRIVACIDAD, "privacy-page");
