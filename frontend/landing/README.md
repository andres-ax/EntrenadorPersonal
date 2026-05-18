# EntrenadorAX Landing

Astro 5 + Tailwind 4 + React. Sitio publico estatico optimizado para SEO.

## Setup

```bash
cd frontend/landing
npm install
cat > .env <<EOF
PUBLIC_BOT_USERNAME=entrenadorax_bot
PUBLIC_SITE_URL=https://entrenadorpersonal-production.up.railway.app
PUBLIC_PLAUSIBLE_DOMAIN=entrenadorpersonal-production.up.railway.app
EOF
npm run dev
```

## Build & deploy a Cloudflare Pages

```bash
npm run build
wrangler pages deploy dist --project-name entrenadorax-landing
```

Railway ya expone el servicio en `entrenadorpersonal-production.up.railway.app`.
Para dominio custom: agregar en Railway > Settings > Domains y apuntar CNAME
desde tu DNS provider. Luego setea `PUBLIC_SITE_URL` con el dominio nuevo.

## Paginas generadas

- `/` - Landing principal (hero + 8 secciones)
- `/deportes` - Listado de 20+ deportes (linkea a paginas individuales)
- `/deportes/[slug]` - Pagina SEO por deporte (long-tail)
- `/politicas/privacidad`
- `/politicas/terminos`
- `/politicas/manejo-datos-tca`

Sitemap automatico en `/sitemap-index.xml`.

## SEO

- OpenGraph + Twitter Cards via `astro-seo`
- Sitemap automatico via `@astrojs/sitemap`
- Lighthouse target >95 (Astro lo facilita por defecto)
- Lazy load de imagenes con `astro:assets` (cuando subas las reales)

## Variables de entorno

- `PUBLIC_BOT_USERNAME` - username del bot Telegram (sin @)
- `PUBLIC_PLAUSIBLE_DOMAIN` - dominio en Plausible Analytics (opcional)
- `PUBLIC_API_BASE_URL` - URL del backend (para `/api/public/precios`)
