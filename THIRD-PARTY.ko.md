# HK-RetroPort 1.1 제3자 구성요소

dos.js 및 dos.html은 GPL-2.0-only입니다. 그 밖의 자체 런처에 적용한 PolyForm Noncommercial 1.0.0은 제3자 저작물의 권리를 제한하지 않습니다. 제품은 LinuxServer.io 또는 게임 제작자의 공식 배포본과 독립적으로 제공됩니다.

| 구성 | 버전·출처 | 조건과 처리 |
|---|---|---|
| DOSBox-X, Wine | Debian trixie의 dosbox-x 2025.02.01+dfsg-3, wine 10.0~repack-6 | GPL/LGPL 및 개별 파일 고지를 유지합니다. 설치 버전별 Debian 패치와 빌드 규칙은 .dsc 및 대응 소스 아카이브에 있습니다. |
| js-dos | https://github.com/caiiiycuk/js-dos/releases/tag/v8.5.4 | npm 8.5.4, GPL-2.0 표기. emulators 8.5.3과 하위 DOSBox WASM을 사용합니다. 배포 시 프런트엔드 결합 범위와 번들 자산 조건을 함께 확인합니다. |
| QUASI88 | https://github.com/toyoshim/quasi88nc/tree/67a3123847b93633379e0a6c07cad2ca4f7d2d2f | 상위 BSD-3-Clause 고지에 더해 cisc의 fmgen과 구형 MAME 음원 코드가 포함됩니다. 비상업 배포, 저작자 고지, 해당 파생 소스 제공 조건을 적용합니다. Makefile.wasm을 사용하며 코어 소스 수정은 없습니다. |
| VBMouse | https://git.javispedro.com/cgit/vbados.git/tag/?h=v0.67 | Javier S. Pedro. DOS 및 Windows 드라이버 GPL-2.0-or-later. 버전 0.67 플로피에서 두 파일을 추출합니다. |
| WebNP2 / NP2kai | https://github.com/uraraworks/WebNP2/tree/0fe85a59622645740dfb4cdb6abd59c8bb3c927b/public/core | 운영자가 따로 설치합니다. 지원 파일과 함께 AZO의 LICENSE.NP2kai를 검증합니다. |
| Selkies와 LinuxServer 기반 | https://github.com/linuxserver/docker-baseimage-selkies/tree/6379480bcbd4ba42c1f5d4ab5eca49304fdedf83 | Dockerfile에 기록한 이미지 다이제스트를 사용합니다. Selkies 2.2.1, pixelflux 2.2.3, pcmflux 2.2.1 및 Debian 패키지에는 개별 라이선스가 적용됩니다. |
| Windows, 상용 게임, 사용자 세이브와 게임별 설정 | 운영자 외부 데이터 | 공개 소스나 로컬 기본 이미지에 동봉하지 않습니다. |

소스 ZIP에는 프로젝트에서 작성한 코드·설정과 공식 PolyForm 라이선스 전문이 들어 있습니다. 빌드 후 완성 이미지에는 위 프로젝트 외의 전이 의존성도 들어갑니다. Afterpiece 테마는 Keefer Rourke의 GPL-3.0-or-later입니다. 로컬 완성 이미지에 포함된 /proot-apps/ncat은 7.94SVN 사전 빌드이며 정확한 소스 리비전을 특정하지 못했습니다. 공개 Docker 이미지에는 해당 기반 레이어를 넣지 않고 설치 시 가져옵니다.
