# Windows에 처음 설치하기

이 안내는 Intel·AMD 64비트 Windows PC 한 대를 게임 서버로 사용하는 운영자용입니다. 플레이어는 웹 브라우저만 준비하면 됩니다.

## 1. Docker Desktop 준비

1. [Docker 공식 Windows 설치 안내](https://docs.docker.com/desktop/setup/install/windows-install/)에서 **Docker Desktop for Windows – x86_64**를 받습니다. WSL 2 백엔드와 Linux 컨테이너를 사용합니다.
2. 설치 프로그램에서 요청하면 Windows를 다시 시작합니다. Docker Desktop을 열고 엔진이 시작될 때까지 기다립니다.
3. PowerShell에서 아래 두 명령을 실행합니다. 첫 결과가 `linux`이고 두 번째에 Compose 버전이 표시되면 준비된 것입니다.

```powershell
docker info --format '{{.OSType}}'
docker compose version
```

## 2. HK-RetroPort 설치

1. [GitHub Releases](https://github.com/danhk0612/HK-RetroPort/releases/tag/v1.1.0)의 **HK-RetroPort-1.1.0.zip**을 받아 쓰기 가능한 폴더에 풉니다. 예를 들어 `C:\Retro\HK-RetroPort`를 사용할 수 있습니다.
2. 탐색기에서 **compose.yaml과 이미지 TAR 파일이 함께 보이는 폴더**를 엽니다. 주소창에 `powershell`을 입력하고 Enter를 누릅니다.
3. 아래 명령을 한 줄씩 실행합니다. 최초 빌드에는 인터넷 연결이 필요합니다.

```powershell
docker load -i hk-retroport-app-1.1-linux-amd64.tar
docker compose build launcher
```

4. **게임과 설정이 함께 담긴 초기 구성팩**을 받았다면 지금 [새 설치에 구성팩 복원하기](game-packs.md#새-설치에-구성팩-복원하기)로 이동합니다. 빈 목록으로 시작하거나 게임별 ZIP을 받았다면 아래 명령으로 관리자 비밀번호를 정하고 서비스를 시작합니다.

```powershell
docker compose run --rm admin-password
docker compose up -d
docker compose ps
```

5. [운영자 페이지](http://localhost:18099/library/manage/)에서 `admin`과 방금 정한 비밀번호로 로그인합니다. [플레이어 페이지](http://localhost:18098/library/)도 열어 봅니다. 처음에는 게임 목록이 비어 있습니다.

## 3. 게임 직접 추가 또는 게임별 팩 적용

**DOS 게임**은 한 게임의 실행 파일·데이터·하위 폴더를 함께 준비합니다. 게임별 ZIP이나 7z를 받았다면 그대로 사용할 수 있습니다. 여러 게임의 ZIP을 모은 배포 묶음이라면 바깥 포장만 풀어 게임별 파일을 꺼냅니다.

1. 운영자 페이지의 **게임 가져오기**에서 게임 폴더 또는 ZIP·7z를 선택하고 **미리보기**를 누릅니다.
2. 제목과 기종을 확인하고 **시작 명령**을 지정합니다. 예를 들어 원래 `PLAY_HAN.BAT`로 한글 드라이버와 사운드를 준비한 뒤 EXE를 실행했다면 그 BAT를 선택합니다.
3. **목록에 등록**을 누르고 플레이어 페이지를 새로고침합니다. **플레이**를 누른 뒤 화면을 클릭해 키보드와 소리를 활성화합니다.
4. 조작과 소리를 확인하고 게임 안에서 저장합니다. 런처에서 종료한 뒤 같은 브라우저로 다시 열어 저장이 이어지는지 확인합니다.

| 기종 | 추가 준비 |
|---|---|
| PC-98 | 디스크 이미지와 게임에 필요한 글꼴·ROM을 준비합니다. 브라우저 실행은 운영자 페이지의 **실행기 관리**에서 안내한 코어 파일을 설치합니다. |
| PC-88 | 디스크와 필요한 ROM을 준비합니다. 기본 데이터 경로에서 ROM의 위치는 `data\library\Emulator\M88`입니다. |
| Windows | 기본 데이터 경로의 `data\collections\windows` 아래에 게임별 폴더를 만들고 파일을 넣습니다. `docker compose restart launcher` 후 운영자 페이지에서 시작 EXE를 확인합니다. 설치된 Windows가 필요한 게임은 `data\collections\.base\win95.img` 또는 `win98.img`를 준비합니다. |

## 4. 다른 PC에서 접속하기

기본 주소는 서버 PC에서만 열립니다. 같은 네트워크에서 접속하려면 서버에서 `ipconfig`로 LAN IPv4 주소를 확인합니다. `compose.yaml` 옆의 `.env` 파일에 아래 항목을 추가하거나 기존 값을 수정합니다. 예시 IP를 서버의 실제 주소로 바꾸세요.

```ini
RETROPORT_LISTEN=192.168.0.20
```

`docker compose up -d`를 다시 실행하고 플레이어에게 `http://192.168.0.20:18098/library/`를 전달합니다. 연결이 막히면 Windows 방화벽의 개인 네트워크에서 TCP 18098의 인바운드 허용 여부를 확인합니다. 운영자 페이지는 서버 PC에서 엽니다.

서버 실행 게임의 세이브는 방문자별 서버 폴더에, 브라우저 직접 실행 게임의 세이브는 플레이어의 브라우저 사이트 데이터에 저장됩니다. 플레이어에게는 처음부터 계속 사용할 접속 주소를 알려 주세요.
