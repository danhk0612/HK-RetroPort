# 게임팩 만들기와 적용하기

| 받는 사람이 원하는 결과 | 제작자가 준비할 파일 | 적용 시점 |
|---|---|---|
| 사용 중인 목록에 게임 추가 | 게임별 ZIP·7z와 시작 명령 안내 | 운영자 페이지에서 가져오기 |
| 새 서버에 같은 게임 목록·실행 설정 구성 | 게임 파일과 카탈로그·설정을 묶은 초기 구성팩 | 런처 이미지 빌드 후, 첫 서비스 시작 전 |

팩 이름과 배포 폴더 이름은 제작자가 정합니다. 아래의 `starter-library.tar.gz`는 명령 예시에 사용한 파일명입니다. HK-RetroPort 공개 설치본은 빈 라이브러리로 시작합니다.

## 게임별 추가팩 만들기

1. 한 게임을 빈 폴더에 준비합니다. 시작 BAT·COM·EXE와 필요한 데이터, 하위 폴더 구조를 유지합니다. 제작자의 플레이 기록이 섞이지 않도록 초기 상태의 게임 파일을 사용합니다.
2. DOS 게임이라면 게임 폴더를 열고 그 **안의 파일과 하위 폴더**를 함께 선택해 ZIP 또는 7z 하나로 압축합니다. 여러 게임은 각각 압축합니다.
3. 배포 안내에 게임명·기종·시작 명령·필요한 디스크나 글꼴을 적습니다. 예를 들어 “DOS / 시작 명령 PLAY.BAT / 첫 화면에서 소리 확인”처럼 작성합니다.
4. 빈 테스트 목록에서 **게임 가져오기 → 미리보기 → 목록에 등록**으로 시험합니다. 실행과 저장까지 확인한 파일을 전달합니다. 받는 사람은 [게임 직접 추가](windows-setup.md#3-게임-직접-추가-또는-게임별-팩-적용)와 같은 절차로 등록합니다.

## 게임과 설정을 묶은 초기 구성팩 만들기

아래는 **HK-RetroPort 1.1.0, Windows PowerShell, 기본 데이터 경로** 기준입니다. 게임 파일·ROM·글꼴·코어·Windows 이미지 중 받는 사람에게 제공할 권리가 있는 항목만 포함하세요. 별도 준비가 필요한 파일은 설치 위치와 함께 팩 안내에 적습니다.

1. 빈 데이터 폴더로 제작 전용 런처를 시작합니다. 배포할 게임만 등록하고 제목·명령·디스크·글꼴·기종별 설정을 저장합니다. 시험 플레이에서 만든 세이브가 게임 원본이나 디스크 이미지 안에 들어 있다면 배포용 원본으로 되돌립니다.
2. `compose.yaml`이 있는 폴더에서 아래 명령을 실행합니다. 게임을 저장하고 종료한 다음 서비스를 내려 SQLite 카탈로그와 게임 파일이 같은 시점에 복사되도록 합니다. `RETROPORT_DATA`를 설정했다면 첫 줄의 `./data`를 실제 제작용 데이터 경로로 바꿉니다.

```powershell
$sourceData = (Resolve-Path './data').Path
$packDir = (New-Item -ItemType Directory -Path './pack-output' -Force).FullName
docker compose down
docker run --rm --network none --entrypoint tar -v "${sourceData}:/source:ro" -v "${packDir}:/out" hk-retroport:1.1 -czf /out/starter-library.tar.gz -C /source collections library settings cores
```

명령이 성공하면 `pack-output\starter-library.tar.gz`가 생깁니다. 같은 이름으로 다시 만들면 이전 출력 파일을 교체합니다. 제작 서버는 `docker compose up -d`로 다시 시작할 수 있습니다.

| 포함하는 폴더 | 받는 서버에서 복원되는 내용 |
|---|---|
| `collections`, `library` | 등록된 게임, 디스크, 미디어 및 그 경로에 넣은 ROM·OS 이미지 |
| `settings`, `cores` | 게임 ID와 카탈로그, 전체·게임별 설정, 운영자가 설치한 코어 |

운영 중인 서버의 `players`에는 방문자 세이브가, `identity`에는 방문자 식별 키가 들어 있습니다. `admin-auth`는 운영자 인증 정보, `operator`는 시험 환경과 게임별 쓰기 사본입니다. 위 명령은 이 폴더들을 제외합니다. 운영자 시험 환경에서만 설치한 Windows 게임은 새 서버의 플레이어로도 시작되는지 확인하세요. 필요한 설치 상태는 제공 가능한 기본 디스크나 게임 데이터에 준비해야 합니다.

3. 팩에는 **테스트한 런처 버전**, 게임 목록, 별도 준비 파일, 아래 복원 안내를 동봉합니다. 완성본을 다른 빈 데이터 폴더에 한 번 복원해 목록과 설정, 대표 게임의 입력·소리·저장을 확인합니다. 런처 설치 파일은 해당 버전의 [공식 릴리스](https://github.com/danhk0612/HK-RetroPort/releases)에서 받을 수 있습니다.

## 새 설치에 구성팩 복원하기

1. [Windows 설치 안내](windows-setup.md)에 따라 Docker Desktop을 준비하고 HK-RetroPort의 **이미지 빌드까지** 마칩니다. 제작자가 명시한 버전을 사용합니다.
2. 신뢰하는 제작자의 구성팩을 `compose.yaml` 옆에 놓습니다. 아래 예시는 `starter-library.tar.gz`이고, 기본 데이터 경로 `./data`가 아직 없는 새 설치를 가정합니다. 기존 서버에 게임을 더할 때는 게임별 추가팩을 사용하세요. 구성팩에는 자체 카탈로그가 있어 기존 목록과 자동 병합되지 않습니다.
3. 같은 폴더의 PowerShell에서 복원합니다. 아래 명령은 새 데이터 폴더를 만들 수 있을 때만 진행합니다.

```powershell
$pack = (Resolve-Path './starter-library.tar.gz' -ErrorAction Stop).Path
$targetData = (New-Item -ItemType Directory -Path './data' -ErrorAction Stop).FullName
docker run --rm --network none --entrypoint tar -v "${pack}:/pack.tar.gz:ro" -v "${targetData}:/restore" hk-retroport:1.1 -xzf /pack.tar.gz -C /restore
```

4. 복원 명령이 성공한 뒤 운영자가 새 비밀번호를 정하고 서비스를 시작합니다. 복원이 중단됐다면 생성된 데이터 폴더를 별도 이름으로 보관하고 빈 경로에서 다시 복원합니다.

```powershell
docker compose run --rm admin-password
docker compose up -d
```

[플레이어 페이지](http://localhost:18098/library/)에서 팩의 게임 목록을 확인합니다. 이 시점부터 서버 세이브와 설정 변경은 받는 사람의 데이터 폴더에 기록됩니다. 운영 중인 서버를 개인적으로 이전하면서 기존 방문자 세이브까지 유지하려면 [저장과 백업](../README.md#저장과-백업)을 따르세요.
