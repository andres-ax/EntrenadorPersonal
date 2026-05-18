# EntrenadorAX Admin Panel

Panel administrativo Next.js 15 (App Router) + TypeScript + Tailwind +
Tanstack Query. Conecta al backend FastAPI en `/admin/*`.

## Setup local

```bash
cd frontend/admin
npm install
echo "NEXT_PUBLIC_API_BASE_URL=https://api.entrenadorax.com" > .env.local
npm run dev
```

Abre http://localhost:3001/login con un admin creado via:

```bash
python scripts/crear_admin.py --email tu@email.com --password "secreta" --rol super
```

## Build & deploy Railway

```bash
npm run build
npm start
```

`output: "standalone"` en `next.config.mjs` permite un Docker minimal:

```dockerfile
FROM node:20-alpine
WORKDIR /app
COPY . .
RUN npm ci && npm run build
ENV PORT=3001
EXPOSE 3001
CMD ["npm", "start"]
```

Variables de entorno necesarias:
- `NEXT_PUBLIC_API_BASE_URL` (URL del bot-api)

## Paginas

- `/login` - email + password
- `/` - dashboard KPIs
- `/usuarios` - lista + filtros
- `/usuarios/[uid]` - detalle + acciones (asignar plan, pausar, bloquear)
- `/pagos` - cola de comprobantes con filtros por estado
- `/pagos/[id]` - revision + aprobar/rechazar
- `/crisis` - log de crisis con niveles
- `/finanzas` - MRR, ingresos por metodo, usuarios por plan
- `/operaciones` - broadcast a usuarios
- `/admins` - gestion de admins (solo rol super)
