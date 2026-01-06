import { NavLink } from "react-router-dom";
import {
  LayoutDashboard,
  Plug,
  PlayCircle,
  FileText,
  Settings,
} from "lucide-react";
import { cn } from "@/lib/utils";

const navItems = [
  { to: "/", icon: LayoutDashboard, label: "Dashboard" },
  { to: "/connectors", icon: Plug, label: "Connectors" },
  { to: "/strategies", icon: PlayCircle, label: "Strategies" },
  { to: "/logs", icon: FileText, label: "Logs" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

export function Sidebar() {
  return (
    <aside className="hidden border-r bg-muted/40 md:block md:w-[220px] lg:w-[280px]">
      <div className="flex h-full max-h-screen flex-col gap-2">
        <nav className="grid items-start px-2 py-4 text-sm font-medium lg:px-4">
          {navItems.map(({ to, icon: Icon, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 transition-all hover:text-primary",
                  isActive
                    ? "bg-muted text-primary"
                    : "text-muted-foreground"
                )
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </div>
    </aside>
  );
}
