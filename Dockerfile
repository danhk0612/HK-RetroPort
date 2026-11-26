FROM emscripten/emsdk:4.0.20 AS pc88
WORKDIR /src
RUN git init \
    && git fetch --depth 1 https://github.com/toyoshim/quasi88nc.git 67a3123847b93633379e0a6c07cad2ca4f7d2d2f \
    && git checkout --detach FETCH_HEAD \
    && make -j4 -f Makefile.wasm

FROM debian:trixie-slim AS df3text
RUN apt-get update && apt-get install -y --no-install-recommends gcc-mingw-w64-i686-posix
COPY df3text.c df3text.def /src/
RUN i686-w64-mingw32-gcc -march=i486 -Os -shared -nostdlib -Wl,--entry,0,--subsystem,windows:4.0 \
    -o /DF3KR.DLL /src/df3text.c /src/df3text.def -lgdi32 -luser32 -lkernel32

FROM ghcr.io/linuxserver/baseimage-selkies:debiantrixie@sha256:8ec2ec5f81bc444643838fe3eea79f0e2ba09f6afff4b6f5b39f3e7cc05efcd1

RUN apt-get update \
    && apt-get install -y --no-install-recommends dosbox-x python3 \
    && rm -rf /var/lib/apt/lists/*

RUN dpkg --add-architecture i386 \
    && apt-get update \
    && apt-get install -y --no-install-recommends wine wine32:i386 libasound2-plugins:i386 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/retroport
COPY --from=pc88 /src/web/quasi88.js /src/web/quasi88.wasm /src/LICENSE ./cores/
COPY --from=pc88 /src/src/fmgen/readme.txt ./notices/fmgen.txt
COPY --from=pc88 /src/src/snddrv/mame.txt ./notices/mame.txt
RUN apt-get update && apt-get install -y --no-install-recommends python3-libarchive-c python3-pil python3-docker && rm -rf /var/lib/apt/lists/*
RUN mkdir -p cores/jsdos && curl -fLsS --retry 3 https://registry.npmjs.org/js-dos/-/js-dos-8.5.4.tgz -o /tmp/jsdos.tgz \
    && tar -xzf /tmp/jsdos.tgz -C cores/jsdos --strip-components=2 package/dist && rm /tmp/jsdos.tgz
RUN apt-get update && apt-get install -y --no-install-recommends mtools libgl1:i386 libgl1-mesa-dri:i386 && rm -rf /var/lib/apt/lists/*
COPY *.py *.html *.js *.conf icon.png LICENSE THIRD-PARTY.ko.md ./
RUN mkdir -p cores/notices && cp /usr/share/common-licenses/GPL-2 cores/notices/GPL-2.txt && cp LICENSE THIRD-PARTY.ko.md cores/notices/ && cp cores/LICENSE notices/*.txt cores/notices/
COPY --chmod=755 init-data.sh /custom-cont-init.d/50-retroport-data
COPY --from=df3text /DF3KR.DLL ./
RUN curl -fsSL https://depot.javispedro.com/vbox/vbados/releases/vbados_0_67.flp -o /tmp/vbados.flp \
    && echo "0f62845235e7d1b062317350e4ac2c649c2a55c135c605517a451530fafddb6a  /tmp/vbados.flp" | sha256sum -c - \
    && mcopy -i /tmp/vbados.flp ::/vbmouse.drv ./VBMOUSE.DRV \
    && mcopy -i /tmp/vbados.flp ::/vbmouse.exe ./VBMOUSE.EXE && rm /tmp/vbados.flp
RUN sed -i '/<\/applications>/i\  <application class="explorer.exe" title="* - Wine Desktop"><decor>no</decor><fullscreen>yes</fullscreen></application>' /etc/xdg/openbox/rc.xml
RUN printf '%s\n' '#!/bin/sh' 'exec /usr/bin/python3 /opt/retroport/service.py' > /defaults/autostart \
    && chmod 755 /defaults/autostart \
    && printf '%s\n' 'location ~ ^/library/cores/(emnp21kai_sdl2[.](js|wasm)|LICENSE[.]NP2kai)$ {' '  alias /operator-cores/0fe85a59622645740dfb4cdb6abd59c8bb3c927b/$1;' '}' 'location = /library/icon.png {' '  alias /opt/retroport/icon.png;' '}' 'location /library/cores/ {' '  alias /opt/retroport/cores/;' '}' 'location /library/ {' '  client_max_body_size 2048m;' '  proxy_read_timeout 600s;' '  proxy_set_header Host $http_host;' '  proxy_set_header X-Forwarded-Proto $scheme;' '  proxy_pass http://127.0.0.1:8090;' '}' > /defaults/retroport-nginx.conf \
    && sed -i '/^  location SUBFOLDER {/i\  include /defaults/retroport-nginx.conf;' /defaults/default.conf

LABEL org.opencontainers.image.title="HK-RetroPort" org.opencontainers.image.licenses="LicenseRef-Mixed" org.opencontainers.image.version="1.1" org.opencontainers.image.authors="HK-RetroPort contributors" org.opencontainers.image.vendor="HK-RetroPort" org.opencontainers.image.description="Independent web launcher for operator-supplied games" org.opencontainers.image.source="https://github.com/danhk0612/HK-RetroPort" org.opencontainers.image.url="" org.opencontainers.image.documentation="" maintainer="HK-RetroPort contributors"
