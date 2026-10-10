import { StockChat } from "@/components/StockChat";

export default function ChatPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-brand-primary">Stock chat</h1>
      <StockChat />
    </div>
  );
}
