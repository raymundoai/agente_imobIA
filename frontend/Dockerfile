# Production image for one of the two front ends, chosen at build time:
#   APP=agency   → painel da imobiliária (index.html)
#   APP=platform → painel admin (platform.html, served as index.html)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG APP=agency
RUN if [ "$APP" = "platform" ]; then \
      npm run build:platform && mv dist-platform out && mv out/platform.html out/index.html; \
    else \
      npm run build && mv dist out; \
    fi

FROM nginx:1.27-alpine
COPY --from=build /app/out /usr/share/nginx/html
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
# Address of the API inside the Docker network; /api/* is forwarded there.
ENV BACKEND_UPSTREAM=backend:8000
EXPOSE 80
