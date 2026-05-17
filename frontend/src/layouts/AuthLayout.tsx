import React from "react";
import { Link, Outlet } from "react-router-dom";

export const AuthLayout: React.FC = () => {
  return (
    <div className="min-h-screen bg-canvas relative overflow-hidden">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[60vh] bg-[radial-gradient(ellipse_at_top,_#fbe1d1_0%,_transparent_55%)] opacity-70"
      />
      <header className="relative z-10 mx-auto flex w-full max-w-[1280px] items-center justify-between px-6 pt-8 sm:px-10">
        <Link
          to="/"
          className="font-display text-2xl tracking-[-0.02em] text-ink"
        >
          Relohelp
        </Link>
        <Link
          to="/login"
          className="text-sm text-muted-stone hover:text-ink transition-colors"
        >
          Sign in
        </Link>
      </header>
      <main className="relative z-10 flex min-h-[calc(100vh-96px)] items-center justify-center px-4 py-12 sm:px-6 lg:px-8">
        <div className="w-full max-w-md space-y-8">
          <Outlet />
        </div>
      </main>
    </div>
  );
};
