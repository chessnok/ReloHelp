import React from "react";
import { Link } from "react-router-dom";
import { MessageCircle, Map, Sparkles, ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";

const features = [
  {
    icon: MessageCircle,
    title: "Talk it through",
    body: "Get answers from an assistant that knows visas, housing, and the small stuff.",
  },
  {
    icon: Map,
    title: "Plan the move",
    body: "Map out timelines, paperwork, and budget across every step of relocating.",
  },
  {
    icon: Sparkles,
    title: "Personal guidance",
    body: "Tailored next steps based on where you're going and what matters to you.",
  },
];

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();

  return (
    <div className="flex flex-col gap-12">
      <section className="surface-warm-mist relative overflow-hidden rounded-[28px] px-8 py-14 sm:px-14 sm:py-20">
        <div
          aria-hidden
          className="absolute -right-24 -top-24 h-72 w-72 rounded-full bg-canvas/40 blur-3xl"
        />
        <div className="relative max-w-3xl">
          <p className="text-[13px] font-medium uppercase tracking-[0.18em] text-terracotta">
            {user?.email ? `Welcome, ${user.email}` : "Welcome back"}
          </p>
          <h1 className="font-display mt-4 text-[44px] leading-[1.05] tracking-[-0.025em] text-ink sm:text-[64px]">
            Your move,
            <br />
            answered clearly.
          </h1>
          <p className="mt-6 max-w-xl text-[17px] leading-[1.5] text-muted-stone">
            A calm, focused workspace for everything that goes into relocating —
            paperwork, decisions, and what to do next.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            <Button asChild size="lg">
              <Link to="/chat">
                Open chat
                <ArrowRight className="ml-1 size-4" />
              </Link>
            </Button>
            <Button asChild variant="outline" size="lg">
              <Link to="/chat">Browse templates</Link>
            </Button>
          </div>
        </div>
      </section>

      <section className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {features.map((feature) => {
          const Icon = feature.icon;
          return (
            <article
              key={feature.title}
              className="surface-canvas shadow-steep rounded-3xl p-7"
            >
              <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-fog text-ink">
                <Icon className="size-5" />
              </div>
              <h2 className="font-display mt-6 text-[24px] leading-tight tracking-tight text-ink">
                {feature.title}
              </h2>
              <p className="mt-3 text-[15px] leading-[1.55] text-muted-stone">
                {feature.body}
              </p>
            </article>
          );
        })}
      </section>

      <section className="surface-fog rounded-3xl px-8 py-10 sm:px-12">
        <div className="flex flex-col items-start justify-between gap-6 sm:flex-row sm:items-center">
          <div className="max-w-xl">
            <h2 className="font-display text-[28px] leading-tight tracking-tight text-ink">
              Ready when you are.
            </h2>
            <p className="mt-2 text-[15px] text-muted-stone">
              Pick up where you left off, or start a fresh conversation.
            </p>
          </div>
          <Button asChild size="lg">
            <Link to="/chat">
              Continue
              <ArrowRight className="ml-1 size-4" />
            </Link>
          </Button>
        </div>
      </section>
    </div>
  );
};
