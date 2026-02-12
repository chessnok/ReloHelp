import React, { createContext, useContext, useEffect, useState } from "react";
import { authApi } from "../api/auth";
import type { User } from "../api/auth";
import { setLogoutCallback } from "../api/client";

import type { LoginData, RegisterData } from "../api/auth";

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (data: LoginData) => Promise<void>;
  register: (data: RegisterData) => Promise<void>;
  logout: () => Promise<void>;
  checkAuth: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const handleLogout = () => {
    setUser(null);
  };

  // Register logout callback for axios interceptor
  useEffect(() => {
    setLogoutCallback(handleLogout);
  }, []);

  const checkAuth = async () => {
    try {
      const userData = await authApi.getMe();
      setUser(userData);
    } catch {
      setUser(null);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    checkAuth();
  }, []);

  const login = async (data: LoginData) => {
    const response = await authApi.login(data);
    setUser(response.user);
  };

  const register = async (data: RegisterData) => {
    await authApi.register(data);
  };

  const logout = async () => {
    try {
      await authApi.logout();
    } catch (error) {
      console.error("Logout error:", error);
      // Continue with logout even if API call fails
    } finally {
      setUser(null);
    }
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, register, logout, checkAuth }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
