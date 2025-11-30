"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useState } from "react";
import { ROUTES } from "@/lib/routes";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import {
  LayoutDashboard,
  LogOut,
  Menu,
  X
} from "lucide-react";

interface AppShellProps {
  children: ReactNode;
  userEmail?: string | null;
  onSignOut?: () => void;
}

export function AppShell({ children, userEmail, onSignOut }: AppShellProps) {
  const pathname = usePathname();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-background">
      {/* Mobile Header */}
      <div className="lg:hidden flex items-center justify-between p-4 border-b bg-background sticky top-0 z-20">
        <span className="font-semibold">RAG Engine</span>
        <Button variant="ghost" size="icon" onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}>
          {isMobileMenuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </Button>
      </div>

      {/* Sidebar Overlay (Mobile) */}
      {isMobileMenuOpen && (
        <div 
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed inset-y-0 left-0 z-40 w-64 transform bg-card border-r border-border transition-transform duration-200 lg:static lg:translate-x-0",
          isMobileMenuOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-14 items-center border-b border-border px-6 font-semibold">
            RAG Engine
          </div>

          <nav className="flex-1 space-y-1 p-4">
            <Link
              href={ROUTES.workspaces}
              onClick={() => setIsMobileMenuOpen(false)}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors hover:bg-accent hover:text-accent-foreground",
                pathname.startsWith(ROUTES.workspaces)
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground"
              )}
            >
              <LayoutDashboard className="h-4 w-4" />
              Workspaces
            </Link>
          </nav>

          <div className="border-t border-border p-4">
             {userEmail && (
                <div className="mb-4 px-2 text-xs text-muted-foreground truncate" title={userEmail}>
                  {userEmail}
                </div>
             )}
             <Button
                variant="outline"
                className="w-full justify-start gap-2"
                onClick={onSignOut}
              >
                <LogOut className="h-4 w-4" />
                Sign Out
              </Button>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 overflow-auto bg-background">
        <div className="container mx-auto p-4 lg:p-8">
           {children}
        </div>
      </main>
    </div>
  );
}
