import React from "react";
import { useAuth } from "@/context/AuthContext";

export const DashboardPage: React.FC = () => {
  const { user } = useAuth();

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">Dashboard</h1>
      <p className="text-muted-foreground">
        Welcome{user?.email ? `, ${user.email}` : ""}. You are logged in.
      </p>
      <p className="text-sm text-muted-foreground mt-4">
        This is a minimal template. Add your app content here.
      </p>
    </div>
  );
};
