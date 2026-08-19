import pino from 'pino';
import { config } from '../config';

/**
 * Singleton structured logger. Use this instead of console.log everywhere.
 */
export const logger = pino({
  level: config.nodeEnv === 'test' ? 'silent' : 'info',
  transport:
    config.nodeEnv === 'development'
      ? { target: 'pino-pretty', options: { colorize: true } }
      : undefined,
});
