<p align="center"><img src="icon.png" width="96" height="96" alt="HK-RetroPort 아이콘"></p>

# HK-RetroPort

브라우저에서 DOS, PC-88, PC-98, Windows 고전 게임을 즐기는 셀프호스팅 런처입니다. 운영자가 PC나 NAS에 게임을 등록하면 플레이어는 웹 주소 하나로 접속해 게임을 고를 수 있습니다. 게임 파일, 운영체제 이미지, ROM과 글꼴은 운영자가 준비합니다.

[최신 버전 다운로드](https://github.com/danhk0612/HK-RetroPort/releases/latest)

## 처음 시작하기

- **새 Windows PC에 설치할 때**는 Docker Desktop 준비부터 첫 게임 등록, 다른 PC에서 접속하는 방법까지 순서대로 따라가세요. [Windows 설치와 첫 게임 등록](docs/windows-setup.md)
- **게임팩을 만들거나 받았을 때**는 기존 목록에 게임을 추가할지, 새 서버에 게임과 설정을 함께 복원할지 선택하세요. [게임팩 제작과 적용](docs/game-packs.md)

## 플레이어용 안내

1. 운영자에게 받은 주소에서 제목을 검색하거나 장르·기종으로 목록을 좁힙니다. 같은 작품에 여러 판본이 있으면 원하는 판본을 선택합니다.
2. **플레이**를 누릅니다. 시작 버튼이 보이면 한 번 더 누르고 게임 화면을 클릭해 키보드와 소리를 활성화합니다. 마우스가 게임에 고정되면 **Esc**로 해제할 수 있습니다.
3. 게임 안에서 먼저 저장한 뒤 런처의 **종료** 버튼으로 나옵니다. 다음에 같은 사이트 주소와 브라우저 프로필로 접속하면 이어서 할 수 있습니다.

브라우저 직접 실행 게임은 해당 브라우저에, 서버 실행 게임은 방문자별 서버 폴더에 저장됩니다. 시크릿 창, 사이트 데이터 삭제 또는 주소 변경으로 저장에 접근하지 못할 수 있습니다. 한 PC를 여러 명이 쓰면 브라우저 프로필을 나눠 주세요.

## 운영자용 빠른 설치

Linux/amd64 컨테이너를 지원하는 Docker Engine과 Docker Compose가 필요합니다. Windows에서는 Docker Desktop의 Linux 컨테이너로 실행할 수 있습니다. 첫 빌드는 인터넷 연결이 필요합니다.

1. Releases에서 **HK-RetroPort-1.1.0.zip**을 받아 빈 폴더에 풉니다.
2. 그 폴더에서 다음 명령을 순서대로 실행합니다.

```sh
docker load -i hk-retroport-app-1.1-linux-amd64.tar
docker compose build launcher
docker compose run --rm admin-password
docker compose up -d
```

저장소를 직접 복제한 경우에는 두 번째 명령부터 실행하세요. 소스 빌드는 PC-88 코어도 직접 컴파일합니다.

| 접속 대상 | 기본 주소 | 용도 |
|---|---|---|
| 플레이어 | http://localhost:18098/library/ | 로그인 없이 게임 선택·실행 |
| 운영자 | http://localhost:18099/library/manage/ | 계정 **admin**으로 게임·실행기·설정 관리 |

운영자 비밀번호는 `docker compose run --rm admin-password`로 다시 설정할 수 있습니다. 새 설치의 게임 목록은 비어 있습니다.

## 첫 게임 등록

**관리 → 게임 가져오기**에서 DOS 게임 폴더 또는 ZIP·7z를 선택합니다. **미리보기**에서 기종과 시작 명령을 확인하고 등록하세요. 한글 드라이버나 소리를 준비하는 배치가 있으면 그 배치를 시작 명령으로 선택합니다. 등록한 게임을 시험 실행하고 플레이어 페이지를 새로고침하세요.

| 기종 | 운영자가 준비할 항목 |
|---|---|
| DOS | 게임 폴더, 시작할 BAT·COM·EXE와 필요한 CD 이미지 |
| PC-88 | 게임 디스크 및 필요한 ROM. ROM은 `data/library/Emulator/M88`에 둡니다. |
| PC-98 | 게임 디스크와 필요한 글꼴·사운드 ROM. 브라우저 실행은 **실행기 관리**의 원본 링크에서 안내한 세 파일을 받아 ZIP 또는 개별 파일로 설치합니다. |
| Windows | `data/collections/windows` 안에 게임별 폴더를 만들고 런처를 재시작합니다. 게임에 따라 Wine 또는 설치된 Windows 디스크가 필요합니다. Windows 디스크는 `data/collections/.base/win95.img` 또는 `win98.img`, 필요한 한글 글꼴은 같은 폴더의 `gulim.ttc`를 사용합니다. |

**실행기 준비 중**으로 보이면 관리 화면에서 해당 기종의 코어와 실행 방식을 확인하세요. **운영자 확인 필요**로 표시된 게임은 운영자가 실행을 보류한 항목입니다.

## NAS에서 다른 사람에게 접속 주소 주기

기본 설정은 설치한 컴퓨터에서만 접속할 수 있습니다. 같은 네트워크에 플레이어 포트를 열려면 `compose.yaml` 옆에 `.env`를 두고 데이터 경로를 NAS에 맞게 지정하세요.

```ini
RETROPORT_DATA=/volume1/retroport/data
RETROPORT_LISTEN=0.0.0.0
```

`docker compose up -d`를 다시 실행한 뒤 플레이어에게 `http://NAS주소:18098/library/`를 전달합니다. 관리 포트는 루프백에 바인딩됩니다. 원격 관리는 `ssh -L 18099:127.0.0.1:18099 계정@NAS주소`로 연결한 뒤 로컬 관리 주소를 엽니다. HTTPS 프록시를 사용하는 경우 플레이 포트에 연결하고 Host 헤더와 WebSocket 업그레이드를 전달합니다. 서버 실행 동시 접속 기본값은 4명이며 `RETROPORT_MAX_SESSIONS`로 조정합니다.

## 저장과 백업

게임과 서버 데이터는 Docker 이미지 밖의 `data`에 보관합니다. 백업할 때는 게임을 저장·종료하고 `docker compose down`으로 서비스를 내린 뒤 데이터 폴더 전체를 복사하세요. 이후 `docker compose up -d`로 다시 시작합니다.

| 폴더 | 내용 |
|---|---|
| `collections`, `library` | 게임·디스크·운영체제 이미지·ROM |
| `settings`, `cores` | 등록 목록·실행 설정·추가 코어 |
| `players`, `identity` | 서버 세이브와 방문자 식별 키. 복구할 때 함께 보존합니다. |
| `operator`, `admin-auth` | 운영자 시험 환경과 관리자 암호 해시 |

서버 백업에는 각 플레이어 브라우저의 로컬 세이브가 포함되지 않습니다.

## 라이선스

HK-RetroPort의 자체 코드는 PolyForm Noncommercial 1.0.0을 적용합니다. DOS 브라우저 연결 파일 `dos.js`와 `dos.html`은 GPL-2.0-only이며, 제3자 코어와 라이브러리는 각 저작자의 조건을 따릅니다. 공개 ZIP에는 해당 배포 이미지의 대응 소스와 고지문을 함께 제공합니다.

[자체 코드 라이선스](LICENSE) · [GPL-2.0 전문](COPYING-GPL-2) · [제3자 고지](THIRD-PARTY.ko.md)
