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
    <div className="flex min-h-screen flex-col bg-canvas">
      <nav className="sticky top-0 z-30 flex h-16 shrink-0 items-center border-b border-border/60 bg-canvas/85 px-4 backdrop-blur-md">
        <div className="mx-auto flex w-full max-w-[1280px] items-center justify-between">
          <div className="flex items-center gap-10">
            <Link
              to="/"
              className="font-display text-[22px] tracking-[-0.02em] text-ink"
            >
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
                      "inline-flex items-center gap-2 rounded-full px-4 py-2 text-[14px] font-medium tracking-tight transition-colors",
                      isActive
                        ? "bg-ink text-canvas"
                        : "text-muted-stone hover:bg-fog hover:text-ink",
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
          !isChat &&
            "mx-auto w-full max-w-[1280px] px-4 py-10 sm:px-6 lg:px-10",
        )}
      >
        <Outlet />
      </main>
    </div>
  );
};
