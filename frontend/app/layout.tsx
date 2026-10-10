import type { Metadata } from "next";
import { IBM_Plex_Sans_Arabic, Inter } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import brand from "@/lib/brand.generated.json";
import "./globals.css";

const inter = Inter({ variable: "--font-sans", subsets: ["latin"] });

const plexArabic = IBM_Plex_Sans_Arabic({
  variable: "--font-plex-arabic",
  subsets: ["arabic"],
  weight: ["400", "500", "600", "700"],
});

export const metadata: Metadata = {
  title: brand.name,
  description: brand.tagline_en,
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" dir="ltr" className={`${inter.variable} ${plexArabic.variable}`}>
      <body className="antialiased">
        <div className="flex min-h-screen">
          <Sidebar />
          <main className="flex-1 px-8 py-6">{children}</main>
        </div>
      </body>
    </html>
  );
}
