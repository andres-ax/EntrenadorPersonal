/**
 * Chat widget demo para la landing de EntrenadorAX.
 * Boton flotante bottom-right que abre un panel de chat.
 * POST /api/public/chat-demo con {mensaje, session_id}.
 * Despues de 3 mensajes muestra CTA a Telegram.
 */
(function () {
  "use strict";

  var sessionId = null;
  var isOpen = false;
  var sending = false;

  function createWidget() {
    // Contenedor principal
    var container = document.createElement("div");
    container.id = "ax-chat-widget";
    container.innerHTML = [
      // Boton flotante
      '<button id="ax-chat-btn" aria-label="Hablar con el coach" style="',
        'position:fixed;bottom:20px;right:20px;z-index:9999;',
        'width:60px;height:60px;border-radius:50%;border:none;cursor:pointer;',
        'background:linear-gradient(135deg,#1c3d8a,#3679f5);',
        'box-shadow:0 4px 20px rgba(31,90,216,0.4);',
        'display:flex;align-items:center;justify-content:center;',
      '">',
        '<img src="/static/img/coach-avatar.png" alt="" style="width:44px;height:44px;border-radius:50%;object-fit:cover;" />',
      '</button>',

      // Panel de chat
      '<div id="ax-chat-panel" style="',
        'display:none;position:fixed;bottom:90px;right:20px;z-index:9998;',
        'width:360px;max-width:calc(100vw - 40px);height:480px;max-height:70vh;',
        'background:#fff;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.15);',
        'flex-direction:column;overflow:hidden;border:1px solid #e2e8f0;',
        'font-family:Inter,system-ui,sans-serif;',
      '">',
        // Header
        '<div style="',
          'background:linear-gradient(135deg,#1c3d8a,#1f5ad8);',
          'color:#fff;padding:14px 16px;display:flex;align-items:center;gap:10px;',
        '">',
          '<img src="/static/img/coach-avatar.png" alt="" style="width:36px;height:36px;border-radius:50%;object-fit:cover;" />',
          '<div>',
            '<div style="font-weight:700;font-size:14px;">EntrenadorAX</div>',
            '<div style="font-size:11px;opacity:0.8;">Coach IA - Prueba gratis</div>',
          '</div>',
          '<button id="ax-chat-close" style="margin-left:auto;background:none;border:none;color:#fff;cursor:pointer;font-size:20px;line-height:1;" aria-label="Cerrar">&times;</button>',
        '</div>',

        // Mensajes
        '<div id="ax-chat-messages" style="',
          'flex:1;overflow-y:auto;padding:12px;display:flex;flex-direction:column;gap:8px;',
          'background:#f8fafc;',
        '"></div>',

        // Input
        '<div style="padding:10px 12px;border-top:1px solid #e2e8f0;background:#fff;display:flex;gap:8px;">',
          '<input id="ax-chat-input" type="text" placeholder="Escribe un mensaje..." maxlength="500" style="',
            'flex:1;padding:10px 14px;border:1px solid #e2e8f0;border-radius:12px;',
            'font-size:14px;outline:none;font-family:inherit;',
          '" />',
          '<button id="ax-chat-send" style="',
            'padding:10px 16px;background:#1f5ad8;color:#fff;border:none;border-radius:12px;',
            'font-weight:600;font-size:14px;cursor:pointer;white-space:nowrap;font-family:inherit;',
          '">Enviar</button>',
        '</div>',
      '</div>',
    ].join("");
    document.body.appendChild(container);

    // Evento toggle
    document.getElementById("ax-chat-btn").addEventListener("click", toggle);
    document.getElementById("ax-chat-close").addEventListener("click", toggle);

    // Enter para enviar
    document.getElementById("ax-chat-input").addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
    });
    document.getElementById("ax-chat-send").addEventListener("click", send);

    // Mensaje inicial del bot
    addMessage("bot", "Hola! Soy EntrenadorAX, tu coach IA. Escribe algo para probar como funciono. Por ejemplo: \"Hago crossfit 3 veces por semana\"");
  }

  function toggle() {
    isOpen = !isOpen;
    var panel = document.getElementById("ax-chat-panel");
    panel.style.display = isOpen ? "flex" : "none";
    if (isOpen) {
      document.getElementById("ax-chat-input").focus();
    }
  }

  function addMessage(role, text) {
    var container = document.getElementById("ax-chat-messages");
    var bubble = document.createElement("div");
    var isBot = role === "bot";
    bubble.style.cssText = [
      "max-width:85%;padding:10px 14px;border-radius:14px;font-size:13px;line-height:1.5;",
      "word-wrap:break-word;",
      isBot ? "align-self:flex-start;background:#e2e8f0;color:#1e293b;" : "align-self:flex-end;background:#1f5ad8;color:#fff;",
    ].join("");
    bubble.textContent = text;
    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
  }

  function addCTA(url) {
    var container = document.getElementById("ax-chat-messages");
    var cta = document.createElement("a");
    cta.href = url;
    cta.target = "_blank";
    cta.rel = "noopener";
    cta.style.cssText = [
      "display:block;margin:8px auto;padding:12px 20px;",
      "background:linear-gradient(135deg,#1c3d8a,#3679f5);color:#fff;",
      "border-radius:12px;font-size:14px;font-weight:700;text-align:center;",
      "text-decoration:none;box-shadow:0 2px 10px rgba(31,90,216,0.3);",
    ].join("");
    cta.textContent = "Continuar en Telegram (gratis)";
    container.appendChild(cta);
    container.scrollTop = container.scrollHeight;
  }

  function addTyping() {
    var container = document.getElementById("ax-chat-messages");
    var typing = document.createElement("div");
    typing.id = "ax-typing";
    typing.style.cssText = "align-self:flex-start;padding:10px 14px;border-radius:14px;background:#e2e8f0;font-size:12px;color:#94a3b8;";
    typing.textContent = "Escribiendo...";
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  }

  function removeTyping() {
    var t = document.getElementById("ax-typing");
    if (t) t.remove();
  }

  function send() {
    if (sending) return;
    var input = document.getElementById("ax-chat-input");
    var msg = (input.value || "").trim();
    if (!msg) return;
    input.value = "";
    addMessage("user", msg);
    sending = true;
    addTyping();

    fetch("/api/public/chat-demo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mensaje: msg, session_id: sessionId }),
    })
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (data) {
        removeTyping();
        sessionId = data.session_id;
        addMessage("bot", data.respuesta);
        if (data.cta_url) {
          addCTA(data.cta_url);
        }
        if (data.restantes === 0) {
          document.getElementById("ax-chat-input").disabled = true;
          document.getElementById("ax-chat-send").disabled = true;
          document.getElementById("ax-chat-input").placeholder = "Continua en Telegram!";
        }
      })
      .catch(function (err) {
        removeTyping();
        addMessage("bot", "Ups, tuve un error. Intenta de nuevo en un momento.");
        console.error("chat-demo error", err);
      })
      .finally(function () {
        sending = false;
      });
  }

  // Inicializar cuando el DOM este listo
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", createWidget);
  } else {
    createWidget();
  }
})();
