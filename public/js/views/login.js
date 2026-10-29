import { h, toast } from "../dom.js";
import { api, auth } from "../api.js";
import { loadUser, state } from "../state.js";

function normalize(raw) {
  const t = raw.replace(/[\s\-()]/g, "");
  if (t.startsWith("+")) return t;
  if (/^3\d{9}$/.test(t)) return "+57" + t;  // celular colombiano sin prefijo
  return t;
}

export async function loginView(_, ctx) {
  const root = h("div", { class: "stack" });
  let phone = "";

  const stepPhone = () => {
    const input = h("input", { id: "phone", type: "tel", inputmode: "tel", autocomplete: "tel", placeholder: "300 123 4567 o +57…", required: true });
    const invite = state.config.beta ? h("input", { id: "invite", type: "password", autocomplete: "off", placeholder: "Clave que te entregó el equipo", required: true }) : null;
    const err = h("div", { class: "err", role: "alert" });
    const btn = h("button", { class: "btn block", type: "submit" }, state.config.otp_on_screen ? "Obtener código" : "Enviar código");
    const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
      e.preventDefault(); err.textContent = ""; btn.disabled = true;
      phone = normalize(input.value);
      try {
        const r = await api.post("/auth/otp/request", { phone, invite: invite ? invite.value.trim() : undefined });
        stepCode(r.dev_code);
      } catch (x) { err.textContent = x.message; btn.disabled = false; }
    } },
      h("div", { class: "field" }, h("label", { for: "phone" }, "Tu celular"), input,
        h("div", { class: "hint" }, state.config.otp_on_screen ? "En esta fase de pruebas el código se muestra en pantalla." : "Te enviaremos un código por mensaje para verificar tu número.")),
      invite && h("div", { class: "field" }, h("label", { for: "invite" }, "Clave de acceso a la beta"), invite), err, btn);
    const creating = (state.next || "").startsWith("/admin");
    root.replaceChildren(h("h1", null, "Entrar"),
      creating && h("p", { class: "muted", id: "login-why" }, "Para crear y administrar tu rifa primero verificamos tu celular. Al terminar volverás al formulario."),
      form);
    input.focus();
  };

  const stepCode = (devCode) => {
    const code = h("input", { id: "code", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, pattern: "\\d{6}", placeholder: "••••••", required: true });
    const name = h("input", { id: "name", autocomplete: "name", placeholder: "Opcional si ya tienes cuenta", maxlength: 80 });
    const accept = h("input", { id: "accept", type: "checkbox" });
    const err = h("div", { class: "err", role: "alert" });
    const btn = h("button", { class: "btn block", type: "submit" }, "Verificar");
    const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
      e.preventDefault(); err.textContent = "";
      if (state.config.terms_required && !accept.checked) { err.textContent = "Para continuar acepta los términos y la política de privacidad."; return; }
      btn.disabled = true;
      try {
        const r = await api.post("/auth/otp/verify", { phone, code: code.value.trim(), name: name.value.trim() || "Usuario", accept_terms: accept.checked });
        auth.set(r.access_token);
        await loadUser();
        toast("Sesión iniciada");
        const next = state.next; state.next = null;
        ctx.go(next || "/");
      } catch (x) { err.textContent = x.message; btn.disabled = false; code.select(); }
    } },
      h("p", null, devCode ? "Verificando el número " : "Enviamos un código a ", h("b", null, phone), "."),
      devCode && h("p", { class: "chip warn", "data-testid": "dev-code" }, "Beta · tu código es " + devCode),
      h("div", { class: "field" }, h("label", { for: "code" }, "Código de 6 dígitos"), code),
      h("div", { class: "field" }, h("label", { for: "name" }, "Tu nombre"), name),
      h("label", { class: "check", for: "accept" }, accept, h("span", null, "Acepto los ", h("a", { href: "#/terminos", target: "_blank", rel: "noopener" }, "términos y condiciones"), " y la ", h("a", { href: "#/privacidad", target: "_blank", rel: "noopener" }, "política de privacidad"), ".")),
      err, btn,
      h("p", null, h("button", { class: "btn ghost small", type: "button", onclick: stepPhone }, "Cambiar número")));
    root.replaceChildren(h("h1", null, "Verifica tu número"), form);
    code.focus();
  };

  stepPhone();
  return root;
}
