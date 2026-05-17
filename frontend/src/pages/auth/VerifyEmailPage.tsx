import React, { useEffect, useState } from "react";
import { useSearchParams, useNavigate, Link } from "react-router-dom";
import { authApi } from "../../api/auth";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import axios from "axios";

export const VerifyEmailPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token");
  const [status, setStatus] = useState<"loading" | "success" | "error">(
    "loading",
  );
  const [message, setMessage] = useState("");

  useEffect(() => {
    const verify = async () => {
      if (!token) {
        setStatus("error");
        setMessage("No verification token provided.");
        return;
      }

      try {
        await authApi.verifyEmail(token);
        setStatus("success");
        // Redirect to login after successful verification
        setTimeout(() => {
          navigate("/login");
        }, 2000);
      } catch (error) {
        setStatus("error");
        if (axios.isAxiosError(error) && error.response?.data?.detail) {
          setMessage(error.response.data.detail);
        } else {
          setMessage("Failed to verify email.");
        }
      }
    };

    verify();
  }, [token, navigate]);

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Email verification</CardTitle>
        <CardDescription>Confirming your email address</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col items-center justify-center py-8">
        {status === "loading" && (
          <div className="flex flex-col items-center space-y-4">
            <Loader2 className="h-10 w-10 animate-spin text-ink" />
            <p className="text-muted-stone">Verifying…</p>
          </div>
        )}
        {status === "success" && (
          <div className="flex flex-col items-center space-y-4 text-ink">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-warm-mist">
              <CheckCircle2 className="h-7 w-7 text-terracotta" />
            </div>
            <p className="font-display text-2xl tracking-tight">
              Email verified
            </p>
          </div>
        )}
        {status === "error" && (
          <div className="flex w-full flex-col items-center space-y-4">
            <div className="flex h-14 w-14 items-center justify-center rounded-full bg-fog">
              <XCircle className="h-7 w-7 text-destructive" />
            </div>
            <p className="font-display text-2xl tracking-tight text-ink">
              Verification failed
            </p>
            <Alert variant="destructive" className="w-full">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{message}</AlertDescription>
            </Alert>
          </div>
        )}
      </CardContent>
      {status === "success" && (
        <CardFooter className="flex justify-center pt-2">
          <p className="text-sm text-muted-stone">Redirecting to sign in…</p>
        </CardFooter>
      )}
      {status === "error" && (
        <CardFooter className="flex justify-center pt-2">
          <Link
            to="/login"
            className="text-sm text-ink underline-offset-4 hover:underline"
          >
            Go to sign in
          </Link>
        </CardFooter>
      )}
    </Card>
  );
};
