import React from "react";
import { useNavigate } from "react-router-dom";
import { MessageSquarePlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChat } from "@/context/ChatContext";

export const ChatIndexPage: React.FC = () => {
  const { createChat } = useChat();
  const navigate = useNavigate();

  const handleNewChat = () => {
    const id = createChat();
    navigate(`/chat/${id}`);
  };

  return (
    <div className="flex h-full flex-col items-center justify-center gap-8 bg-canvas px-6 text-center">
      <div className="flex size-16 items-center justify-center rounded-full bg-warm-mist">
        <MessageSquarePlus className="size-7 text-terracotta" />
      </div>
      <div className="space-y-3">
        <h2 className="font-display text-[40px] leading-[1.05] tracking-[-0.025em] text-ink">
          How can I help you today?
        </h2>
        <p className="mx-auto max-w-md text-[15px] leading-[1.55] text-muted-stone">
          Start a new conversation, or pick up one from the sidebar.
        </p>
      </div>
      <Button size="lg" onClick={handleNewChat}>
        <MessageSquarePlus className="size-4" />
        New chat
      </Button>
    </div>
  );
};
