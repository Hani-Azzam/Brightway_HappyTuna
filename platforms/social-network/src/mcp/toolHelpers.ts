import { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { AppError } from '../utils/errors';
import { logger } from '../utils/logger';

/**
 * Wraps a value as a successful MCP tool result: the data is JSON-serialized into a single text
 * content block. Prisma `Date`s serialize to ISO strings automatically.
 */
export function jsonResult(data: unknown): CallToolResult {
  return { content: [{ type: 'text', text: JSON.stringify(data, null, 2) }] };
}

/**
 * Wraps a message as a failed MCP tool result (`isError: true`) so the calling model sees the
 * failure without the request itself erroring out.
 */
export function errorResult(message: string): CallToolResult {
  return { content: [{ type: 'text', text: message }], isError: true };
}

/**
 * Runs a tool's business logic and normalizes the outcome into a `CallToolResult`. An operational
 * `AppError` thrown by a service becomes a clean error result carrying its status code and message;
 * any other (unexpected) error is logged and reported generically so no stack trace leaks to the model.
 */
export async function runTool(fn: () => Promise<unknown>): Promise<CallToolResult> {
  try {
    return jsonResult(await fn());
  } catch (err) {
    if (err instanceof AppError) {
      return errorResult(`Error ${err.statusCode}: ${err.message}`);
    }
    logger.error({ err }, 'Unexpected error in MCP tool');
    return errorResult('Internal error while executing tool');
  }
}
