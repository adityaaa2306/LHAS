# Frontend Dockerfile - LHAS React Application
# Multi-stage build for optimal image size

# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# API URL for build-time configuration
# Use localhost:8000 since the browser will access through host machine ports
ARG VITE_API_URL=http://localhost:8000

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Build the app with API URL
RUN VITE_API_URL=${VITE_API_URL} npm run build

# Runtime stage - minimal node-based image
FROM node:20-alpine

WORKDIR /app

# Install serve to run the production build
RUN npm install -g serve

# Copy built app from builder
COPY --from=builder /app/dist ./dist

# Expose port
EXPOSE 3000

# Environment variables
ENV NODE_ENV=production
ENV VITE_API_URL=${VITE_API_URL:-http://backend:8000}

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Serve the app on port 3000
CMD ["serve", "-s", "dist", "-l", "3000"]
