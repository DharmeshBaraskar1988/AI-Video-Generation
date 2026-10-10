"use client";

import { useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

/** Deletes a script with its video job, narration, renders and log (after a confirm). */
export function DeleteScriptButton({
  videoId,
  label,
  disabled,
  compact,
  onDeleted,
}: {
  videoId: string;
  label: string;
  disabled?: boolean;
  compact?: boolean;
  onDeleted: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function remove(e: React.MouseEvent) {
    e.preventDefault(); // the button may sit inside a link card
    e.stopPropagation();
    if (
      !window.confirm(
        `Delete the script for ${label}? Its narration, videos and log are deleted too. This cannot be undone.`,
      )
    )
      return;
    setBusy(true);
    try {
      await api(`/api/scripts/${videoId}`, { method: "DELETE" });
      onDeleted();
    } catch (err) {
      window.alert(`Delete failed: ${(err as Error).message}`);
      setBusy(false);
    }
  }

  return (
    <Button
      size={compact ? "icon-sm" : "sm"}
      variant="ghost"
      className="text-loss hover:text-loss"
      disabled={disabled || busy}
      onClick={remove}
      aria-label="Delete script"
      title={disabled ? "Wait until the job finishes" : "Delete script"}
    >
      {busy ? <Loader2 className="animate-spin" /> : <Trash2 />}
      {!compact && "Delete"}
    </Button>
  );
}
