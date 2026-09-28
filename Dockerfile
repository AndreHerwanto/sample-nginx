FROM nginx:alpine
COPY default.conf /etc/nginx/conf.d/default.conf
COPY index.html.tpl /usr/share/nginx/template/index.html.tpl
COPY 40-render-index.sh /docker-entrypoint.d/40-render-index.sh
RUN chmod +x /docker-entrypoint.d/40-render-index.sh
