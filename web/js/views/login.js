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
    const err = h("div", { class: "err", role: "alert" });
    const btn = h("button", { class: "btn block", type: "submit" }, "Enviar código");
    const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
      e.preventDefault(); err.textContent = ""; btn.disabled = true;
      phone = normalize(input.value);
      try {
        const r = await api.post("/auth/otp/request", { phone });
        stepCode(r.dev_code);
      } catch (x) { err.textContent = x.message; btn.disabled = false; }
    } },
      h("div", { class: "field" }, h("label", { for: "phone" }, "Tu celular"), input,
        h("div", { class: "hint" }, "Te enviaremos un código por mensaje para verificar tu número.")), err, btn);
    root.replaceChildren(h("h1", null, "Entrar"), form);
    input.focus();
  };

  const stepCode = (devCode) => {
    const code = h("input", { id: "code", inputmode: "numeric", autocomplete: "one-time-code", maxlength: 6, pattern: "\\d{6}", placeholder: "••••••", required: true });
    const name = h("input", { id: "name", autocomplete: "name", placeholder: "Opcional si ya tienes cuenta", maxlength: 80 });
    const err = h("div", { class: "err", role: "alert" });
    const btn = h("button", { class: "btn block", type: "submit" }, "Verificar");
    const form = h("form", { class: "card", novalidate: true, onsubmit: async (e) => {
      e.preventDefault(); err.textContent = ""; btn.disabled = true;
      try {
        const r = await api.post("/auth/otp/verify", { phone, code: code.value.trim(), name: name.value.trim() || "Usuario" });
        auth.set(r.access_token);
        await loadUser();
        toast("Sesión iniciada");
        const next = state.next; state.next = null;
        ctx.go(next || "/");
      } catch (x) { err.textContent = x.message; btn.disabled = false; code.select(); }
    } },
      h("p", null, "Enviamos un código a ", h("b", null, phone), "."),
      devCode && h("p", { class: "chip warn", "data-testid": "dev-code" }, "Modo desarrollo · código: " + devCode),
      h("div", { class: "field" }, h("label", { for: "code" }, "Código de 6 dígitos"), code),
      h("div", { class: "field" }, h("label", { for: "name" }, "Tu nombre"), name), err, btn,
      h("p", null, h("button", { class: "btn ghost small", type: "button", onclick: stepPhone }, "Cambiar número")));
    root.replaceChildren(h("h1", null, "Verifica tu número"), form);
    code.focus();
  };

  stepPhone();
  return root;
}
