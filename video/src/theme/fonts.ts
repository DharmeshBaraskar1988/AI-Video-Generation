// Fonts are bundled locally (@fontsource) so rendering never depends on Google Fonts being reachable.
import { loadFont } from "@remotion/fonts";
import inter400 from "@fontsource/inter/files/inter-latin-400-normal.woff2";
import inter500 from "@fontsource/inter/files/inter-latin-500-normal.woff2";
import inter600 from "@fontsource/inter/files/inter-latin-600-normal.woff2";
import inter700 from "@fontsource/inter/files/inter-latin-700-normal.woff2";
import inter800 from "@fontsource/inter/files/inter-latin-800-normal.woff2";
import plex400 from "@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-400-normal.woff2";
import plex500 from "@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-500-normal.woff2";
import plex600 from "@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-600-normal.woff2";
import plex700 from "@fontsource/ibm-plex-sans-arabic/files/ibm-plex-sans-arabic-arabic-700-normal.woff2";

const INTER = "Inter";
const ARABIC = "IBM Plex Sans Arabic";

const faces: [string, string, string][] = [
  [INTER, inter400, "400"],
  [INTER, inter500, "500"],
  [INTER, inter600, "600"],
  [INTER, inter700, "700"],
  [INTER, inter800, "800"],
  [ARABIC, plex400, "400"],
  [ARABIC, plex500, "500"],
  [ARABIC, plex600, "600"],
  [ARABIC, plex700, "700"], // 800 falls back to 700 for Arabic glyphs
];

// loadFont delays rendering until each face is ready.
faces.forEach(([family, url, weight]) => {
  loadFont({ family, url, weight });
});

// Arabic glyphs come from IBM Plex Sans Arabic; Latin letters and digits from Inter.
export const fontFor = (lang: "en" | "ar"): string =>
  lang === "ar" ? `"${ARABIC}", "${INTER}", sans-serif` : `"${INTER}", sans-serif`;
