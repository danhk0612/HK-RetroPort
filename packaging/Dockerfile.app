FROM hk-retroport:1.1 AS compiled
FROM scratch
WORKDIR /opt/retroport
COPY --from=compiled /opt/retroport/icon.png /opt/retroport/*.py /opt/retroport/*.html /opt/retroport/*.js /opt/retroport/*.conf /opt/retroport/DF3KR.DLL ./
COPY --from=compiled /opt/retroport/cores/quasi88.js /opt/retroport/cores/quasi88.wasm /opt/retroport/cores/LICENSE ./cores/
COPY --from=compiled /custom-cont-init.d/50-retroport-data /custom-cont-init.d/50-retroport-data
COPY LICENSE THIRD-PARTY.ko.md ./
COPY --from=compiled /opt/retroport/notices/ ./notices/
COPY packaging/notices/ ./notices/
COPY COPYING-GPL-2 ./notices/
LABEL org.opencontainers.image.title="HK-RetroPort application files" org.opencontainers.image.version="1.1" org.opencontainers.image.licenses="LicenseRef-Mixed"
