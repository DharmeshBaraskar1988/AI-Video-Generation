// Dev helper: bundle once and render a still from the middle of every scene.
// Usage: node scripts/render-stills.mjs <outDir> [browserExecutable]
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const outDir = process.argv[2] ?? join(root, "out", "stills");
const browserExecutable = process.argv[3] ?? null;
mkdirSync(outDir, { recursive: true });

const serveUrl = await bundle({ entryPoint: join(root, "src", "index.ts"), publicDir: join(root, "public") });

for (const [id, file, tag] of [
  ["QuarterlyVideo", "sample.props.json", "en"],
  ["QuarterlyVideoArabic", "sample_ar.props.json", "ar"],
]) {
  const inputProps = JSON.parse(readFileSync(join(root, file), "utf8"));
  const composition = await selectComposition({ serveUrl, id, inputProps, browserExecutable });
  for (const s of inputProps.scenes) {
    const seconds = s.type === "intro" ? 2.5 : s.audioStart + 4;
    const frame = Math.min(composition.durationInFrames - 1, Math.round(seconds * composition.fps));
    const output = join(outDir, `${tag}_${s.id}_${s.type}.png`);
    await renderStill({ serveUrl, composition, inputProps, frame, output, browserExecutable });
    console.log(`${tag} ${s.type} frame ${frame} -> ${output}`);
  }
}
