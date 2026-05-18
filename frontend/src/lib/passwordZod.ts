import * as z from "zod";
import { getPasswordErrors } from "./passwordPolicy";

export const passwordFieldSchema = z.string().superRefine((value, ctx) => {
  for (const message of getPasswordErrors(value)) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message,
    });
  }
});
