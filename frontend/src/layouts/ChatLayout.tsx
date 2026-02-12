import React from "react";
import { Outlet } from "react-router-dom";
import { ChatProvider } from "@/context/ChatContext";
import { ChatSidebar } from "@/components/chat/ChatSidebar";

export const ChatLayout: React.FC = () => {
  return (
    <ChatProvider>
      <div className="flex min-h-0 w-full flex-1">
        <ChatSidebar />
        <main className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </ChatProvider>
  );
};
