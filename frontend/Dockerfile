FROM node:22-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:1.31-alpine AS runtime

RUN apk upgrade --no-cache \
 && rm -f /docker-entrypoint.d/10-listen-on-ipv6-by-default.sh \
 && apk add --no-cache --virtual .build-deps libcap \
 && setcap cap_net_bind_service=+ep /usr/sbin/nginx \
 && apk del .build-deps \
 && mkdir -p /var/cache/nginx /var/run /etc/nginx/templates \
 && touch /var/run/nginx.pid \
 && chown -R nginx:nginx /var/cache/nginx /var/log/nginx /var/run/nginx.pid /etc/nginx/conf.d /etc/nginx/templates /usr/share/nginx/html

COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
ENV BACKEND_ORIGIN="http://backend:8000" \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1
COPY --chown=nginx:nginx nginx.conf /etc/nginx/templates/default.conf.template

USER nginx
EXPOSE 80

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
  CMD wget --quiet --spider --tries=1 http://127.0.0.1/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
