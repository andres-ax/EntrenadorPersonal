# EntrenadorAX Mini App

Mini App de Telegram para EntrenadorAX. Stack: Vite + React 19 + TypeScript +
Tailwind + Recharts + Telegram Web Apps SDK.

## Desarrollo

```bash
cd frontend/miniapp
npm install
echo "VITE_API_BASE_URL=https://entrenadorpersonal-production.up.railway.app" > .env.local
echo "VITE_REALTIME_WS_URL=wss://entrenadorpersonal-production.up.railway.app/ws/realtime" >> .env.local
echo "VITE_BOT_USERNAME=entrenadorax_bot" >> .env.local
npm run dev
```

Para testear dentro de Telegram en desarrollo:

1. Expone tu dev server con `ngrok http 5173` o Cloudflare Tunnel.
2. En `@BotFather` registra la URL HTTPS como Web App del bot.

## Build

```bash
npm run build
```

Genera `dist/` listo para subir a Cloudflare Pages, Vercel, Netlify.

## Deploy a Cloudflare Pages

1. `wrangler pages deploy dist --project-name entrenadorax-miniapp`
2. Por defecto Railway expone el servicio en `entrenadorpersonal-production.up.railway.app`.
   Si tienes dominio custom, agregalo en Railway y apuntalo via CNAME.
3. En backend setea `MINIAPP_URL=https://<tu-dominio-o-railway>.app`.
4. Reinicia el bot (en `post_init` actualiza el `setChatMenuButton`).

## Estructura

- `src/lib/api.ts` - cliente axios + JWT renovacion automatica
- `src/lib/telegram.ts` - bindings al SDK Web App (HapticFeedback, BackButton, etc)
- `src/pages/` - 8 vistas: Dashboard, Calendario, Plan, PRs, Settings, Pagar, Llamar, Wearables
- `src/types/` - interfaces compartidas
- `index.html` carga `telegram-web-app.js` desde Telegram CDN
