# ==========================================
# STAGE 1: Build the Application
# ==========================================
FROM node:22-alpine AS builder
WORKDIR /app

# Copy configuration and package files
COPY package*.json tsconfig.json ./
COPY client/package*.json ./client/

# Install ALL dependencies (including devDependencies like typescript)
RUN npm install
RUN cd client && npm install

# Copy source directories needed for building
COPY prisma ./prisma/
COPY client ./client/
COPY src ./src/
COPY public ./public/

# Generate Prisma Client, build frontend, and build backend
RUN npx prisma generate
RUN cd client && npm run build
RUN npm run build

# Remove development dependencies to keep production light
RUN npm prune --production

# ==========================================
# STAGE 2: Production Run Environment
# ==========================================
FROM node:22-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
# Default sqlite path (relative to prisma/schema.prisma -> /app/prisma/dev.db); ephemeral unless
# overridden with an absolute path into a bind-mounted volume (see README's Docker section).
ENV DATABASE_URL=file:./dev.db

# Copy only what is strictly necessary to run the app from Stage 1
COPY package*.json ./
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY --from=builder /app/public ./public
COPY --from=builder /app/prisma ./prisma
# src is needed at runtime only for seeding: prisma/seed.ts is run via tsx (not precompiled)
# and imports from ../src/config and ../src/utils/text.
COPY --from=builder /app/src ./src

COPY docker-entrypoint.sh ./
RUN chmod +x ./docker-entrypoint.sh

# Open port 3000
EXPOSE 3000

# Runs migrations, seeds the database only when SEED_DB=true, then starts the app.
# Empty/unseeded by default: docker run -e SEED_DB=true <image> to seed.
CMD ["./docker-entrypoint.sh"]