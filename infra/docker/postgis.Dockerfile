FROM postgis/postgis:17-3.6@sha256:1ac10b2551ba84ae05db8e7da477afcd0a3fede99bcb7705da2ee157390cb095
# gosu is only used by the upstream root -> postgres transition. Run as postgres
# directly; do not ship its old Go runtime or enable a root startup path.
RUN rm /usr/local/bin/gosu
COPY postgis-entrypoint.sh /usr/local/bin/business-ai-postgis-entrypoint
COPY postgis-initialized.sh /docker-entrypoint-initdb.d/99-business-ai-initialized.sh
RUN chmod 755 /usr/local/bin/business-ai-postgis-entrypoint /docker-entrypoint-initdb.d/99-business-ai-initialized.sh
USER postgres
ENTRYPOINT ["business-ai-postgis-entrypoint"]
CMD ["postgres"]
