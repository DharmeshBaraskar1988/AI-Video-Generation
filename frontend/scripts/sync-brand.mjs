// Copies data/brand into the front end so brand.json stays the single source of truth.
// Runs automatically before `npm run dev` and `npm run build`.
import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontend = join(here, "..");
const brandDir = join(frontend, "..", "data", "brand");

const brand = JSON.parse(readFileSync(join(brandDir, "brand.json"), "utf8"));

mkdirSync(join(frontend, "public", "brand"), { recursive: true });
copyFileSync(join(brandDir, "logo.svg"), join(frontend, "public", "brand", "logo.svg"));

const vars = Object.entries(brand.colors)
  .map(([name, hex]) => `  --brand-${name}: ${hex};`)
  .join("\n");
writeFileSync(
  join(frontend, "app", "brand.generated.css"),
  `/* Generated from data/brand/brand.json by scripts/sync-brand.mjs. Do not edit. */\n:root {\n${vars}\n}\n`,
);

writeFileSync(
  join(frontend, "lib", "brand.generated.json"),
  JSON.stringify({ name: brand.name, tagline_en: brand.tagline_en, tagline_ar: brand.tagline_ar }, null, 2) + "\n",
);

console.log(`brand synced: ${Object.keys(brand.colors).join(", ")}`);
