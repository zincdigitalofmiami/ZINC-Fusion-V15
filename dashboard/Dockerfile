# Build stage
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source files
COPY . .

# Build the Vue app with Vite
RUN npm run build

# Production stage
FROM nginx:alpine

# Install envsubst (part of gettext)
RUN apk add --no-cache gettext

# Copy nginx config template
COPY nginx.conf.template /etc/nginx/nginx.conf.template

# Copy startup script
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Copy built assets from builder stage
COPY --from=builder /app/dist /usr/share/nginx/html

# Expose port 80
EXPOSE 80

# Use startup script to inject env vars and start nginx
CMD ["/start.sh"]
