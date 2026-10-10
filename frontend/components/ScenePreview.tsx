import { Fragment } from "react";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { Placeholder, Scene } from "@/lib/scripts";
import { cn } from "@/lib/utils";

const PLACEHOLDER_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

/** Script text with each {{placeholder}} shown as a locked chip holding its verified value. */
export function ScriptText({
  text,
  lang,
  placeholders,
}: {
  text: string;
  lang: "en" | "ar";
  placeholders: Record<string, Placeholder>;
}) {
  const parts = text.split(PLACEHOLDER_RE);
  return (
    <p lang={lang} dir={lang === "ar" ? "rtl" : "ltr"} className="leading-8">
      {parts.map((part, i) => {
        if (i % 2 === 0) return <Fragment key={i}>{part}</Fragment>;
        const p = placeholders[part];
        return (
          <span
            key={i}
            title={p ? `{{${part}}}: ${p.label}${p.derived ? " (derived)" : ""}` : `Unknown placeholder {{${part}}}`}
            className={cn(
              "tabular mx-0.5 inline-block rounded-md border px-1.5 leading-6 whitespace-nowrap",
              !p && "border-loss bg-loss/10 text-loss",
              p && !p.derived && "border-brand-primary/30 bg-brand-primary/10 text-brand-primary",
              p?.derived && "border-dashed border-brand-accent bg-brand-accent/15 text-brand-ink",
            )}
          >
            {p ? (lang === "ar" ? p.display_ar : p.display_en) : `{{${part}}}`}
          </span>
        );
      })}
    </p>
  );
}

export function ScenePreview({
  scene,
  index,
  placeholders,
  issues = [],
}: {
  scene: Scene;
  index: number;
  placeholders: Record<string, Placeholder>;
  issues?: string[];
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-2">
        <CardTitle className="text-base">Scene {index + 1}</CardTitle>
        <Badge variant="outline" className="capitalize">
          {scene.type}
        </Badge>
        {scene.visual?.chart && <Badge variant="outline">{scene.visual.chart}</Badge>}
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid gap-6 md:grid-cols-2">
          <ScriptText text={scene.en} lang="en" placeholders={placeholders} />
          <ScriptText text={scene.ar} lang="ar" placeholders={placeholders} />
        </div>
        {issues.length > 0 && (
          <ul className="rounded-md border border-loss/40 bg-loss/5 p-2 text-xs text-loss">
            {issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
