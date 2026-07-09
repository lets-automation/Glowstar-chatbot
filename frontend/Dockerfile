# Multi-stage: build the Vite SPA, then serve the static output through nginx,
# which also reverse-proxies /api/* to the backend container. That keeps the
# browser talking to ONE origin (this container), so there's no CORS to worry
# about in the deployed stack - only in local `npm run dev` against a separate
# backend port.

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# The built app calls this base URL for all API requests. "/api" (default)
# is same-origin - nginx.conf below proxies it to the backend service.
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
