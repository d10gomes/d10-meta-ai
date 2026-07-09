"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Megaphone, Stethoscope, Zap, Palette,
  BarChart3, Settings, LogOut, Bot,
} from "lucide-react";
import { useAuth } from "@/hooks/useAuth";
import { clsx } from "clsx";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/accounts", label: "Contas Meta", icon: Megaphone },
  { href: "/campaigns", label: "Campanhas", icon: Zap },
  { href: "/agents", label: "Agentes", icon: Bot },
  { href: "/diagnoses", label: "Diagnósticos", icon: Stethoscope },
  { href: "/creatives", label: "Criativos", icon: Palette },
  { href: "/reports", label: "Relatórios", icon: BarChart3 },
  { href: "/settings", label: "Configurações", icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();
  const logout = useAuth((s) => s.logout);

  return (
    <aside className="w-64 bg-surface-card border-r border-surface-border flex flex-col h-screen fixed left-0 top-0">
      <div className="p-6 border-b border-surface-border">
        <h1 className="text-xl font-bold text-brand-500">D10 META AI</h1>
        <p className="text-xs text-gray-500 mt-0.5">Meta Ads Intelligence</p>
      </div>
      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={clsx(
              "flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors",
              pathname === href
                ? "bg-brand-500/10 text-brand-500"
                : "text-gray-400 hover:text-white hover:bg-surface-border"
            )}
          >
            <Icon size={18} />
            {label}
          </Link>
        ))}
      </nav>
      <div className="p-4 border-t border-surface-border">
        <button onClick={logout} className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-white hover:bg-surface-border w-full transition-colors">
          <LogOut size={18} /> Sair
        </button>
      </div>
    </aside>
  );
}
