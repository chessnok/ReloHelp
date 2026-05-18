import * as z from "zod";
import { getPasswordErrors } from "./passwordPolicy";

export const passwordFieldSchema = z.string().superRefine((value, ctx) => {
  const errors = getPasswordErrors(value);
  if (errors.length > 0) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: errors[0],
    });
  }
});
