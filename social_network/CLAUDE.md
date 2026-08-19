# Project Overview
We are building a tuna company run entirely by AI agents.
The company will be tested under a realistic crisis scenario.
For the crisis scenario to be realistic, we need to simulate several real world platforms that shape public perception of the company.
The job of the team you are in, is to build a social media platform, similar to X (formerly known as Twitter), where simulated users (ai bots) discuss events partaining to the company. Events and actions from the company affect users, and vice versa.


## Coding Standards
- Use TypeScript for all new code — no implicit `any` types
- All async functions must use async/await (no .then() chains)
- Error handling: use custom AppError class in src/utils/errors.ts
- All API responses must follow the standard envelope:
  { success: boolean, data?: T, error?: string }
- Use Prisma for all database operations — no raw SQL unless absolutely necessary
- Services layer handles business logic; route handlers only parse input and call services
- All exported functions must have JSDoc comments

## Testing Requirements
- Unit tests for all service layer functions
- Integration tests for all API endpoints
- Test coverage must remain above 80%
- All tests go in __tests__ directories next to the code they test
- Test files must be named: [filename].test.ts

## MUST / Critical Rules
- NEVER commit secrets, API keys, or passwords to git
- NEVER skip running tests before marking a task complete
- NEVER use console.log in production code — use the logger utility (src/utils/logger.ts)

## Preferred Approaches
- Environment variables: access via the config module (src/config.ts), never process.env directly

## Style and Feel
- Bright white with a light blue accent.
- Intuitive and readable.
- Similar to Twitter, the way it was before becoming X.
- Project owner likes to be involved in artistic decision making. Do not hesitate to ask about UI.