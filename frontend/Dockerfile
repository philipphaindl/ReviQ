FROM node:20-alpine AS builder
WORKDIR /app
# Install from the committed lockfile. With package.json alone npm resolved
# every range afresh on each build, so the image depended on the day it was
# built; in October 2026 that resolution crashed npm itself
# ("Cannot read properties of null (reading 'edgesOut')").
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
