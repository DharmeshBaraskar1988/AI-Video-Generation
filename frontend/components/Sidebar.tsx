"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { FileText, FileUp, LayoutDashboard, MessageSquare, ScrollText, Settings, Video } from "lucide-react";
import { cn } from "@/lib/utils";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/documents", label: "Documents", icon: FileUp },
  { href: "/scripts", label: "Scripts", icon: ScrollText },
  { href: "/videos", label: "Videos", icon: Video },
  { href: "/summary", label: "Summary", icon: FileText },
  { href: "/chat", label: "Chat", icon: MessageSquare },
  { href: "/admin", label: "Admin", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="sticky top-0 flex h-screen w-60 shrink-0 flex-col border-e bg-sidebar">
      <Link href="/" className="block px-4 py-5">
        <Image src="/brand/logo.svg" alt="D-Storify" width={208} height={56} priority />
      </Link>
      <nav className="flex flex-col gap-1 px-3">
        {NAV.map(({ href, label, icon: Icon }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href);
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                active
                  ? "bg-sidebar-primary text-sidebar-primary-foreground"
                  : "text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
              )}
            >
              <Icon className="size-4" />
              {label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto border-t px-4 py-3 text-xs text-muted-foreground">Quarterly results POC</div>
    </aside>
  );
}
