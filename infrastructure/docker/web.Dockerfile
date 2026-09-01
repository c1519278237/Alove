FROM nginx:1.29-alpine
COPY apps/mobile/build/web /usr/share/nginx/html
COPY infrastructure/nginx/default.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
