import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export function ComingSoon({ title, step, children }: { title: string; step: number; children: React.ReactNode }) {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-brand-primary">{title}</h1>
      <Card>
        <CardHeader>
          <CardTitle>Coming in Step {step}</CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground">{children}</CardContent>
      </Card>
    </div>
  );
}
