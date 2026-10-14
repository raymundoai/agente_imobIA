FROM nginx:1.27-alpine

COPY index.html styles.css favicon.svg /usr/share/nginx/html/

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD wget -q --spider http://127.0.0.1/ || exit 1
