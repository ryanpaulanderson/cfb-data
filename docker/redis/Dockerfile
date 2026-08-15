FROM redis:8.2-alpine

COPY redis.conf /usr/local/etc/redis/redis.conf

HEALTHCHECK --interval=2s --timeout=2s --start-period=2s --retries=20 \
  CMD ["redis-cli", "--raw", "ping"]

CMD ["redis-server", "/usr/local/etc/redis/redis.conf"]
