import { Response } from 'express';

/**
 * Standard API response envelope.
 */
export interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: string;
}

/** Sends a successful JSON response. */
export function sendSuccess<T>(res: Response, data: T, statusCode = 200): void {
  res.status(statusCode).json({ success: true, data } satisfies ApiResponse<T>);
}

/** Sends an error JSON response. */
export function sendError(res: Response, message: string, statusCode = 500): void {
  res.status(statusCode).json({ success: false, error: message } satisfies ApiResponse<never>);
}
