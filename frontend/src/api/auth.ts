import client from "./client";

export interface User {
  id: string;
  email: string;
  is_active: string;
  roles: string[];
  email_is_verified: boolean;
}

export interface LoginResponse {
  user: User;
}

export interface LoginData {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
}

export interface ResetPasswordData {
  token: string;
  new_password: string;
}

export const authApi = {
  login: async (data: LoginData) => {
    const response = await client.post<LoginResponse>("/auth/login", data);
    return response.data;
  },
  register: async (data: RegisterData) => {
    const response = await client.post("/auth/register", data);
    return response.data;
  },
  logout: async () => {
    await client.post("/auth/logout");
  },
  getMe: async () => {
    const response = await client.get<User>("/auth/me");
    return response.data;
  },
  verifyEmail: async (token: string) => {
    const response = await client.post("/auth/verify-email", { token });
    return response.data;
  },
  forgotPassword: async (email: string) => {
    const response = await client.post("/auth/password/forgot", { email });
    return response.data;
  },
  resetPassword: async (data: ResetPasswordData) => {
    const response = await client.post("/auth/password/reset", data);
    return response.data;
  },
};
