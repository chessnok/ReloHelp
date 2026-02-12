import axios from "axios";

// Use relative URL in production (nginx proxy) or absolute URL in development
const baseURL = import.meta.env.PROD ? "" : "http://localhost:8000/";

// Global logout callback - will be set by AuthContext
let globalLogoutCallback: (() => void) | null = null;

export const setLogoutCallback = (callback: () => void) => {
  globalLogoutCallback = callback;
};

const client = axios.create({
  baseURL,
  withCredentials: true,
  headers: {
    "Content-Type": "application/json",
  },
});

client.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      // If this is already a refresh token request that failed, logout immediately
      if (originalRequest.url === "/auth/token/refresh") {
        // Clear auth cookies
        document.cookie =
          "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
        document.cookie =
          "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";

        // Call logout callback if available
        if (globalLogoutCallback) {
          globalLogoutCallback();
        }

        // Redirect to login
        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }

        return Promise.reject(error);
      }

      // Try to refresh token
      try {
        await client.post("/auth/token/refresh");
        return client(originalRequest);
      } catch (refreshError) {
        // Refresh failed - logout and redirect
        document.cookie =
          "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
        document.cookie =
          "refresh_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";

        if (globalLogoutCallback) {
          globalLogoutCallback();
        }

        if (window.location.pathname !== "/login") {
          window.location.href = "/login";
        }

        return Promise.reject(refreshError);
      }
    }
    return Promise.reject(error);
  },
);

export const apiClient = client;
export default client;
