import { Request, Response, NextFunction } from 'express';
import { AppError } from '../utils/errors';
import { logger } from '../utils/logger';
import { sendError } from '../utils/response';

/**
 * Global Express error handler. Must be registered last.
 */
export function errorHandler(
  err: Error,
  _req: Request,
  res: Response,
  _next: NextFunction,
): void {
  if (err instanceof AppError && err.isOperational) {
    sendError(res, err.message, err.statusCode);
    return;
  }

  logger.error({ err }, 'Unhandled error');
  sendError(res, 'Internal server error', 500);
}
