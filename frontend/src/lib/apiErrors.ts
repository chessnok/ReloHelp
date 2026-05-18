import axios from "axios";

/** Turn FastAPI `detail` (string or validation array) into display text. */
export function formatApiErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return null;
      })
      .filter((msg): msg is string => Boolean(msg));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }
  return fallback;
}

export function isAxiosErrorWithStatus(
  err: unknown,
  status: number,
): err is import("axios").AxiosError<{ detail?: unknown }> {
  return axios.isAxiosError(err) && err.response?.status === status;
}
