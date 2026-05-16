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
    <aside className="flex h-full w-72 flex-col border-r border-border/60 bg-fog">
      <div className="px-4 pt-5 pb-3">
        <Button
          size="default"
          className="w-full justify-center gap-2"
          onClick={handleNewChat}
        >
          <MessageSquarePlus className="size-4 shrink-0" />
          New chat
        </Button>
      </div>
      <div className="px-4 pt-2 pb-1">
        <p className="text-[11px] font-medium uppercase tracking-[0.16em] text-light-steel">
          Recent
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-4">
        <div className="space-y-1">
          {chats.map((chat) => {
            const isActive = chatId === chat.id;
            return (
              <div
                key={chat.id}
                className={cn(
                  "group flex items-center gap-1 rounded-2xl text-[14px] transition-colors",
                  isActive
                    ? "bg-canvas text-ink shadow-[0_1px_2px_rgba(4,23,43,0.06)]"
                    : "text-muted-stone hover:bg-canvas/60 hover:text-ink"
                )}
              >
                <Link
                  to={`/chat/${chat.id}`}
                  className="min-w-0 flex-1 truncate px-4 py-2.5"
                >
                  {chat.title}
                </Link>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="mr-1 size-7 shrink-0 opacity-0 group-hover:opacity-100"
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
