FROM alpine:latest

RUN apk add --no-cache s3cmd

COPY backup-script.sh /backup-script.sh
RUN chmod +x /backup-script.sh

ENTRYPOINT ["/backup-script.sh"]