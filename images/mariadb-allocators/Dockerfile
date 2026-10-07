ARG MARIADB_IMAGE=mariadb:11.8
FROM ${MARIADB_IMAGE}

RUN apt-get update \
    && apt-get install -y --no-install-recommends libjemalloc2 libtcmalloc-minimal4 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
