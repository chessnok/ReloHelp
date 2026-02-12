import React from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { MessageSquarePlus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useChat } from "@/context/ChatContext";
import { cn } from "@/lib/utils";

export const ChatSidebar: React.FC = () => {
  const { chats, createChat, deleteChat } = useChat();
  const { chatId } = useParams<{ chatId: string }>();
  const navigate = useNavigate();

  const handleNewChat = () => {
    const id = createChat();
    navigate(`/chat/${id}`);
  };

  return (
    <aside className="flex h-full w-64 flex-col border-r border-border bg-sidebar">
      <div className="flex items-center gap-2 p-3">
        <Button
          variant="outline"
          size="sm"
          className="flex-1 justify-start gap-2 border-sidebar-border bg-sidebar-accent/50 text-sidebar-foreground hover:bg-sidebar-accent"
          onClick={handleNewChat}
        >
          <MessageSquarePlus className="size-4 shrink-0" />
          New chat
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        <div className="space-y-0.5">
          {chats.map((chat) => {
            const isActive = chatId === chat.id;
            return (
              <div
                key={chat.id}
                className={cn(
                  "group flex items-center gap-1 rounded-lg text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-sidebar-accent/70"
                )}
              >
                <Link
                  to={`/chat/${chat.id}`}
                  className="min-w-0 flex-1 truncate px-3 py-2.5"
                >
                  {chat.title}
                </Link>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="size-7 shrink-0 opacity-0 group-hover:opacity-100"
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    if (chatId === chat.id) navigate("/chat");
                    deleteChat(chat.id);
                  }}
                  aria-label="Delete chat"
                >
                  <Trash2 className="size-3.5" />
                </Button>
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
};
