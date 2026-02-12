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
    <div className="flex h-full flex-col items-center justify-center gap-6 px-4 text-center">
      <div className="flex size-16 items-center justify-center rounded-2xl bg-primary/10">
        <MessageSquarePlus className="size-8 text-primary" />
      </div>
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight">
          How can I help you today?
        </h2>
        <p className="text-muted-foreground max-w-sm">
          Start a new conversation or choose one from the sidebar.
        </p>
      </div>
      <Button size="lg" onClick={handleNewChat} className="gap-2">
        <MessageSquarePlus className="size-4" />
        New chat
      </Button>
    </div>
  );
}
