import { defineConfig } from "astro/config";
import tailwind from "@astrojs/tailwind";
import sitemap from "@astrojs/sitemap";
import react from "@astrojs/react";

// `site` se usa para canonicals, sitemap y Open Graph. Tomamos el valor de
// PUBLIC_SITE_URL si esta seteado (env-aware), si no caemos al dominio
// Railway real (api/landing publica). Cuando se consiga entrenadorax.com
// basta con setear PUBLIC_SITE_URL=https://entrenadorax.com.
const SITE_URL =
  process.env.PUBLIC_SITE_URL ||
  "https://entrenadorpersonal-production.up.railway.app";

export default defineConfig({
  site: SITE_URL,
  output: "static",
  integrations: [tailwind(), sitemap(), react()],
  build: {
    inlineStylesheets: "auto",
  },
});
