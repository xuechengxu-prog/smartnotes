# 多阶段构建：构建阶段
FROM node:18-alpine AS builder
WORKDIR /app
RUN npm config set cache /tmp/npm-cache --global
COPY package.json ./
RUN npm install --no-cache
COPY . .
RUN npm run build

# 运行阶段：使用 nginx:alpine 运行
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
