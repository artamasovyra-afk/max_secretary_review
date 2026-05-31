FROM node:24-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY public/ ./public/
COPY src/ ./src/
RUN npm run build

FROM nginx:stable AS serve

COPY --from=build /app/dist /usr/share/nginx/html

RUN printf '%s\n' \
    'server {' \
    '    listen 80;' \
    '    server_name _;' \
    '    root /usr/share/nginx/html;' \
    '    index index.html;' \
    '' \
    '    location = /site.webmanifest {' \
    '        default_type application/manifest+json;' \
    '        try_files $uri =404;' \
    '    }' \
    '' \
    '    location = /index.html {' \
    '        add_header Cache-Control "no-store";' \
    '        try_files /index.html =404;' \
    '    }' \
    '' \
    '    location /assets/ {' \
    '        add_header Cache-Control "public, max-age=31536000, immutable";' \
    '        try_files $uri =404;' \
    '    }' \
    '' \
    '    location / {' \
    '        add_header Cache-Control "no-store";' \
    '        try_files $uri $uri/ /index.html;' \
    '    }' \
    '}' \
    > /etc/nginx/conf.d/default.conf

EXPOSE 80
