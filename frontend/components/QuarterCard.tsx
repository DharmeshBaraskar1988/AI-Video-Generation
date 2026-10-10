import { Info } from "lucide-react";
import { GenerateButton } from "@/components/GenerateButton";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { formatEps, formatQrMillion, type Quarter } from "@/lib/quarters";
import { cn } from "@/lib/utils";

function Kpi({
  label,
  value,
  derived,
  tone = "neutral",
}: {
  label: string;
  value: string | null;
  derived: boolean;
  tone?: "neutral" | "loss";
}) {
  return (
    <div className="rounded-lg border bg-background/60 p-3">
      <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{label}</span>
        {derived && <span className="italic">derived</span>}
      </div>
      <div className={cn("tabular mt-1 text-xl font-semibold", tone === "loss" ? "text-loss" : "text-brand-ink")}>
        {value ?? <span className="text-sm font-normal text-muted-foreground">not reported</span>}
      </div>
    </div>
  );
}

export function QuarterCard({ company, quarter }: { company: string; quarter: Quarter }) {
  const { revenue, net_profit, eps_qr, derived_fields } = quarter;
  const loss = quarter.is_loss;

  return (
    <Card className={cn(quarter.is_current && "ring-2 ring-brand-accent")}>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="text-lg">{quarter.period}</CardTitle>
          <div className="flex gap-1">
            {quarter.is_current && <Badge className="bg-brand-accent text-brand-ink">Current</Badge>}
            {!quarter.is_single_quarter && <Badge variant="outline">Year to date</Badge>}
            {quarter.derived && <Badge variant="outline">Derived</Badge>}
          </div>
        </div>
        <CardDescription>{quarter.months}</CardDescription>
      </CardHeader>

      <CardContent className="grid gap-2">
        <Kpi
          label="Revenue"
          value={revenue === null ? null : formatQrMillion(revenue)}
          derived={derived_fields.includes("revenue")}
        />
        <Kpi
          label={loss ? "Net loss" : "Net profit"}
          value={net_profit === null ? null : formatQrMillion(net_profit)}
          derived={derived_fields.includes("net_profit")}
          tone={loss ? "loss" : "neutral"}
        />
        <Kpi
          label="EPS"
          value={eps_qr === null ? null : formatEps(eps_qr)}
          derived={derived_fields.includes("eps_qr")}
          tone={eps_qr !== null && eps_qr < 0 ? "loss" : "neutral"}
        />
        {quarter.derived && quarter.derivation && (
          <p className="flex gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" />
            <span>Derived, not reported: {quarter.derivation}</span>
          </p>
        )}
      </CardContent>

      <CardFooter>
        <GenerateButton company={company} period={quarter.id} />
      </CardFooter>
    </Card>
  );
}
