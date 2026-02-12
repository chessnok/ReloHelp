import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
} from "react-router-dom";
import { AuthProvider } from "./context/AuthContext";
import { AuthLayout } from "./layouts/AuthLayout";
import { MainLayout } from "./layouts/MainLayout";
import { ProtectedRoutes } from "./layouts/ProtectedRoutes";
import { LoginPage } from "./pages/auth/LoginPage";
import { RegisterPage } from "./pages/auth/RegisterPage";
import { VerifyEmailPage } from "./pages/auth/VerifyEmailPage";
import { ForgotPasswordPage } from "./pages/auth/ForgotPasswordPage";
import { ResetPasswordPage } from "./pages/auth/ResetPasswordPage";
import { ChatPage } from "./pages/ai/ChatPage";
import { ChatIndexPage } from "./pages/ai/ChatIndexPage";
import { ChatLayout } from "./layouts/ChatLayout";
import { DashboardPage } from "./pages/dashboard/DashboardPage";

function App() {
  return (
    <Router>
      <AuthProvider>
        <Routes>
          {/* Public Auth Routes */}
          <Route element={<AuthLayout />}>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/verify-email" element={<VerifyEmailPage />} />
            <Route path="/forgot-password" element={<ForgotPasswordPage />} />
            <Route path="/reset-password" element={<ResetPasswordPage />} />
          </Route>

          {/* Protected Routes */}
          <Route element={<ProtectedRoutes />}>
            <Route element={<MainLayout />}>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/chat" element={<ChatLayout />}>
                <Route index element={<ChatIndexPage />} />
                <Route path=":chatId" element={<ChatPage />} />
              </Route>
            </Route>
          </Route>

          {/* Catch all */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </AuthProvider>
    </Router>
  );
}

export default App;
