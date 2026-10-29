// E2E móvil: crear rifa -> comprar con comprobante -> aprobar -> cerrar -> sortear -> resultado público.
// Uso: BASE_URL=http://127.0.0.1:8099 PG_DSN=postgresql://... node e2e/e2e.mjs
import { createRequire } from "node:module";
import { execFileSync } from "node:child_process";
import { writeFileSync, mkdirSync } from "node:fs";

const require = createRequire(import.meta.url);
const { chromium, devices } = require(process.env.PLAYWRIGHT_PATH || "playwright");
const BASE = process.env.BASE_URL || "http://127.0.0.1:8099";
const DSN = process.env.PG_DSN;
const OUT = process.env.SHOTS || "e2e/shots";
mkdirSync(OUT, { recursive: true });

// PNG válido mínimo (1x1)
const PNG = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
writeFileSync(`${OUT}/proof.png`, PNG);

const sql = (q) => execFileSync("psql", [DSN, "-Atc", q]).toString().trim();
let failures = 0;
const check = (cond, msg) => { console.log((cond ? "PASS " : "FAIL ") + msg); if (!cond) failures++; };

const browser = await chromium.launch();
const mobile = devices["Pixel 5"];
const problems = [];
async function newUser(name) {
  const ctx = await browser.newContext({ ...mobile, locale: "es-CO", timezoneId: "America/Bogota" });
  const page = await ctx.newPage();
  page.on("console", (m) => { if (m.type() === "error" && !/ERR_INTERNET_DISCONNECTED/.test(m.text())) problems.push(`${name} console: ${m.text()}`); });
  page.on("pageerror", (e) => problems.push(`${name} pageerror: ${e.message}`));
  return { ctx, page };
}
async function login(page, phone, name) {
  await page.goto(BASE + "/#/login");
  await page.fill("#phone", phone);
  if (await page.locator("#invite").count()) await page.fill("#invite", process.env.BETA_KEY || "");
  await page.click("form button[type=submit]");
  const dev = await page.locator("[data-testid=dev-code]").innerText();
  await page.fill("#code", dev.match(/\d{6}/)[0]);
  await page.fill("#name", name);
  await page.click("button:has-text('Verificar')");
  await page.waitForSelector(".who:has-text('" + name + "')");
}

const admin = await newUser("admin"), buyer = await newUser("buyer");
const A = admin.page, B = buyer.page;

// 1. Administrador crea y publica la rifa desde la UI
await login(A, "+573001110001", "Admin");
await A.goto(BASE + "/#/admin/new");
await A.fill("#title", "Rifa E2E");
await A.fill("#terms", "Términos de prueba");
await A.fill("#total", "20"); await A.fill("#per", "1"); await A.fill("#price", "10000");
await A.fill("textarea[aria-label='Descripción'], input[aria-label='Descripción']", "Moto 0km");
await A.fill("input[aria-label='Nequi']", "3001234567");
await A.click("#save-publish");
await A.waitForURL(/#\/admin\/r\//);
const rid = A.url().split("/").pop();
check(sql(`select status from raffles where id='${rid}'`) === "OPEN", "rifa creada y publicada desde la UI");
check(sql(`select count(*) from tickets where raffle_id='${rid}'`) === "20", "20 boletas generadas");
await A.screenshot({ path: `${OUT}/01-admin-rifa.png` });

// 2. Comprador: inicia sesión, elige 2 boletas, paga con referencia + comprobante
await login(B, "+573002220002", "Beto");
await B.goto(BASE + `/#/r/${rid}`);
await B.waitForSelector("#t-3");
await B.screenshot({ path: `${OUT}/02-grilla.png` });
await B.click("#t-3"); await B.click("#t-7");
check(await B.locator("#go-pay").isVisible(), "barra inferior aparece con la selección");
await B.click("#go-pay");
await B.waitForSelector("#proof");
await B.selectOption("#platform", "NEQUI");
await B.fill("#ref", "NQ-E2E-1");
await B.setInputFiles("#proof", `${OUT}/proof.png`);
await B.screenshot({ path: `${OUT}/03-pago.png` });
await B.click("#submit-pay");
await B.waitForSelector("#confirmation");
check(sql(`select count(*) from tickets where raffle_id='${rid}' and status='CONGELADO'`) === "2", "2 boletas CONGELADO tras reportar el pago");
check(sql(`select count(*) from proofs`) === "1", "comprobante almacenado");
await B.screenshot({ path: `${OUT}/04-confirmacion.png` });

// 3. Otro comprador ve las boletas como no disponibles (anónimo, sin sesión)
const anon = await newUser("anon");
await anon.page.goto(BASE + `/#/r/${rid}`);
await anon.page.waitForSelector("#t-3");
check(await anon.page.locator("#t-3").isDisabled(), "boleta reservada no se puede elegir");
await anon.ctx.close();

// 4. Administrador revisa el comprobante y aprueba
await A.goto(BASE + `/#/admin/r/${rid}`);
await A.waitForSelector("[data-tx]");
await A.click("button:has-text('Ver comprobante')");
await A.waitForSelector("dialog img");
check(await A.locator("dialog img").evaluate((i) => i.complete && i.naturalWidth > 0), "el comprobante se muestra al administrador");
await A.screenshot({ path: `${OUT}/05-admin-comprobante.png` });
await A.click("dialog button:has-text('Cerrar')");
await A.click("[data-act=approve]");
await A.waitForSelector("#no-pending");
check(sql(`select count(*) from tickets where raffle_id='${rid}' and status='PAGADO'`) === "2", "boletas PAGADO tras aprobar");

// 5. El comprador ve su compra pagada
await B.goto(BASE + "/#/mine");
await B.waitForSelector("[data-status=APPROVED]");
check(true, "Mis compras muestra el pago aprobado");
await B.screenshot({ path: `${OUT}/06-mis-compras.png` });

// 6. Cierre de ventas (se adelanta la fecha) y sorteo
sql(`update raffles set sales_close_at = now() - interval '1 minute' where id='${rid}'`);
await A.goto(BASE + `/#/admin/r/${rid}`);
await A.click("#close");
await A.waitForSelector("#accounting");
check((await A.locator("#accounting").innerText()).includes("20.000"), "arqueo muestra $20.000 validados");
await A.screenshot({ path: `${OUT}/07-arqueo.png` });
await A.click("#run-draw");
await A.click("dialog button:has-text('Sortear')");
await A.waitForSelector("a:has-text('Ver resultado público')");
check(sql(`select status from raffles where id='${rid}'`) === "DRAWN", "rifa DRAWN");

// 7. Resultado público + ganador notificado
await B.goto(BASE + `/#/r/${rid}`);
await B.waitForSelector("#result");
await B.screenshot({ path: `${OUT}/08-resultado.png` });
const winNum = sql(`select winning_number from draws where raffle_id='${rid}'`);
check((await B.locator("#result").innerText()).includes("Número ganador"), "resultado público visible, ganador " + winNum);
check(sql(`select count(*) from notifications where raffle_id='${rid}' and type='WINNER'`) === "1", "notificación WINNER encolada");

// 8. PWA: manifest, service worker y modo sin conexión
const mf = await (await B.request.get(BASE + "/manifest.webmanifest")).json();
check(mf.display === "standalone" && mf.icons.length >= 2, "manifest instalable");
await B.evaluate(() => navigator.serviceWorker.ready);
await B.reload(); await B.waitForSelector("main");
await buyer.ctx.setOffline(true);
await B.goto(BASE + "/#/"); await B.reload();
await B.waitForSelector(".brand");
check(await B.locator(".brand").isVisible(), "el shell carga sin conexión (service worker)");
await buyer.ctx.setOffline(false);

// 9. Seguridad: cabeceras y CSP sin violaciones
const hdr = (await B.request.get(BASE + "/")).headers();
check(/default-src 'self'/.test(hdr["content-security-policy"] || ""), "CSP presente");
check(problems.length === 0, "sin errores de consola ni violaciones CSP" + (problems.length ? ": " + problems.join(" | ") : ""));

await browser.close();
console.log(failures ? `\n${failures} FALLO(S)` : "\nE2E OK");
process.exit(failures ? 1 : 0);
