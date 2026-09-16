# Production image using Next.js standalone output: only the server bundle and the
# modules it actually needs are copied into the runtime stage.

# ---- Stage 1: dependencies ----
FROM node:24-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- Stage 2: build ----
FROM node:24-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- Stage 3: runtime ----
FROM node:24-alpine AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000

RUN addgroup -g 10001 -S nodegrp && adduser -S -u 10001 -G nodegrp nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodegrp /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodegrp /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

CMD ["node", "server.js"]
