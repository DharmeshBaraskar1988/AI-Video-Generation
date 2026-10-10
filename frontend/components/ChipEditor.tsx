"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";
import type { Placeholder } from "@/lib/scripts";
import { cn } from "@/lib/utils";

const PLACEHOLDER_RE = /\{\{\s*([A-Za-z0-9_]+)\s*\}\}/g;

export type ChipEditorHandle = { insertPlaceholder: (key: string) => void };

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

export function chipClass(p: Placeholder | undefined): string {
  return cn(
    "tabular mx-0.5 inline-block cursor-default select-all rounded-md border px-1.5 leading-6 whitespace-nowrap",
    !p && "border-loss bg-loss/10 text-loss",
    p && !p.derived && "border-brand-primary/30 bg-brand-primary/10 text-brand-primary",
    p?.derived && "border-dashed border-brand-accent bg-brand-accent/15 text-brand-ink",
  );
}

function chipHtml(key: string, placeholders: Record<string, Placeholder>, lang: "en" | "ar"): string {
  const p = placeholders[key];
  const label = p ? (lang === "ar" ? p.display_ar : p.display_en) : `{{${key}}}`;
  const title = p ? `{{${key}}}: ${p.label}${p.derived ? " (derived)" : ""}` : `Unknown placeholder {{${key}}}`;
  return `<span contenteditable="false" data-key="${key}" title="${escapeHtml(title)}" class="${chipClass(p)}">${escapeHtml(label)}</span>`;
}

function toHtml(text: string, placeholders: Record<string, Placeholder>, lang: "en" | "ar"): string {
  let html = "";
  let last = 0;
  for (const m of text.matchAll(PLACEHOLDER_RE)) {
    html += escapeHtml(text.slice(last, m.index));
    html += chipHtml(m[1], placeholders, lang);
    last = (m.index ?? 0) + m[0].length;
  }
  return html + escapeHtml(text.slice(last));
}

/** Turn the editable DOM back into script text: chips become {{key}}. */
function serialize(node: Node): string {
  let out = "";
  node.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) out += child.textContent ?? "";
    else if (child instanceof HTMLElement) {
      if (child.dataset.key) out += `{{${child.dataset.key}}}`;
      else if (child.tagName === "BR") out += " ";
      else out += serialize(child);
    }
  });
  return out.replace(/ /g, " ");
}

type Props = {
  value: string;
  onChange: (text: string) => void;
  lang: "en" | "ar";
  placeholders: Record<string, Placeholder>;
  className?: string;
};

/**
 * Editable scene text. Placeholders are locked chips (contenteditable=false) showing their
 * verified value; they can be deleted or inserted, never typed into.
 */
export const ChipEditor = forwardRef<ChipEditorHandle, Props>(function ChipEditor(
  { value, onChange, lang, placeholders, className },
  ref,
) {
  const el = useRef<HTMLDivElement>(null);
  const lastText = useRef<string | null>(null);
  const savedRange = useRef<Range | null>(null);

  // Re-render only when the value changes from outside (load, regenerate), not while typing.
  useEffect(() => {
    if (el.current && value !== lastText.current) {
      el.current.innerHTML = toHtml(value, placeholders, lang);
      lastText.current = value;
    }
  }, [value, placeholders, lang]);

  const emit = () => {
    if (!el.current) return;
    const text = serialize(el.current);
    lastText.current = text;
    onChange(text);
  };

  const rememberSelection = () => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount && el.current?.contains(sel.anchorNode)) {
      savedRange.current = sel.getRangeAt(0).cloneRange();
    }
  };

  useImperativeHandle(ref, () => ({
    insertPlaceholder(key: string) {
      const root = el.current;
      if (!root) return;
      const tpl = document.createElement("template");
      tpl.innerHTML = chipHtml(key, placeholders, lang);
      const chip = tpl.content.firstChild as Node;
      const space = document.createTextNode(" ");
      const range = savedRange.current;
      if (range && root.contains(range.startContainer)) {
        range.deleteContents();
        range.insertNode(space);
        range.insertNode(chip);
      } else {
        root.append(" ", chip, space);
      }
      const sel = window.getSelection();
      const after = document.createRange();
      after.setStartAfter(space);
      sel?.removeAllRanges();
      sel?.addRange(after);
      savedRange.current = after.cloneRange();
      emit();
    },
  }));

  return (
    <div
      ref={el}
      lang={lang}
      dir={lang === "ar" ? "rtl" : "ltr"}
      contentEditable
      suppressContentEditableWarning
      spellCheck={lang === "en"}
      onInput={emit}
      onKeyUp={rememberSelection}
      onMouseUp={rememberSelection}
      onBlur={() => {
        rememberSelection();
        // Turn any {{key}} typed by hand into a chip.
        if (el.current && /\{\{\s*[A-Za-z0-9_]+\s*\}\}/.test(el.current.innerText)) {
          const text = serialize(el.current);
          el.current.innerHTML = toHtml(text, placeholders, lang);
        }
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.preventDefault(); // a scene is one paragraph
      }}
      onPaste={(e) => {
        e.preventDefault();
        document.execCommand("insertText", false, e.clipboardData.getData("text/plain").replace(/\s+/g, " "));
      }}
      className={cn(
        "min-h-24 rounded-md border bg-background/40 px-3 py-2 leading-8 outline-none focus-visible:ring-2 focus-visible:ring-ring",
        className,
      )}
    />
  );
});
