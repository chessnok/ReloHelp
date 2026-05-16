import React from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { Home, MessageCircle, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

export const MainLayout: React.FC = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const { logout } = useAuth();

  const handleLogout = async () => {
    try {
      await logout();
      navigate("/login");
    } catch (error) {
      console.error("Logout error:", error);
      navigate("/login");
    }
  };

  const navigation = [
    { name: "Home", href: "/", icon: Home },
    { name: "Chat", href: "/chat", icon: MessageCircle },
  ];

  const isChat = location.pathname.startsWith("/chat");

  return (
    <div className="flex min-h-screen flex-col bg-background">
      <nav className="flex h-14 shrink-0 items-center border-b border-border bg-card px-4 shadow-sm">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between">
          <div className="flex items-center gap-8">
            <Link to="/" className="text-lg font-semibold tracking-tight">
              Relohelp
            </Link>
            <div className="hidden gap-1 sm:flex">
              {navigation.map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.href === "/chat"
                    ? location.pathname.startsWith("/chat")
                    : location.pathname === item.href;
                return (
                  <Link
                    key={item.name}
                    to={item.href}
                    className={cn(
                      "inline-flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
                    )}
                  >
                    <Icon className="size-4" />
                    {item.name}
                  </Link>
                );
              })}
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={handleLogout}>
            <LogOut className="mr-2 size-4" />
            Logout
          </Button>
        </div>
      </nav>

      <main
        className={cn(
          "flex-1 min-h-0 flex flex-col",
          !isChat && "mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8",
        )}
      >
        <Outlet />
      </main>
    </div>
  );
};
