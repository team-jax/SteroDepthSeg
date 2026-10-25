# 캘리브레이션 절차

이 문서만 따라 하면 **현재 연결된 폰의 두 렌즈(초광각 2 + 광각 5)** 로 `calib_phone_pair.json` 을 만들고, 이 파일로 미터 단위 depth를 얻을 수 있다.
저장소 구조와 왜 이렇게 하는지는 [doc_REPO_ANALYSIS.md](doc_REPO_ANALYSIS.md)를 참고한다.

모든 명령은 저장소 루트(`/home/leajeajun/Desktop/StereoDepthSeg`)에서 실행한다.

- 캘리 계산: `./venv/bin/python`
- FFS depth 확인: `./venv_ffs/bin/python`

---

## 0. 언제 다시 해야 하나

| 상황 | 할 일 |
|---|---|
| **폰이 바뀜** (기종이 같아도 개체마다 공장값이 다름) | 1~6단계 전부 |
| 폰을 떨어뜨림, 라이브 실행 시 `Phone rectification failed` | 2단계(`--check`) 후 FAIL이면 3~6단계 |
| `--focus-m` 값을 바꿈 | 3~6단계 (광각 fx가 초점 위치에 따라 바뀐다) |
| `--size`(해상도)를 바꿈 | 5단계의 `--target-size` 만 새 해상도로 다시 |

**2026-10-25 현재 `calib_phone_pair.json` 은 Galaxy S25(SM-S931N) 용 `metric` 이다** (보드 39뷰, RMS 0.105 px, baseline 16.64 mm, FFS vs 보드 PnP 거리 +0.8%). 아래 "S25 실제 결과" 참조. 이전 S24 파일은 git 기록에 있다.

## 준비물

- USB 디버깅을 켠 폰 (`adb devices` 에 `device` 로 보일 것)
- 체커보드를 **실제 크기 100%** 로 띄울 화면: 다른 노트북·모니터·태블릿. 이 PC 화면도 되지만 폰이 이 PC에 USB로 묶여 있으니 케이블 길이를 확인할 것.
- 자 (20 cm 이상) — 보드를 이 PC 화면에 띄우면 없어도 된다(4단계, EDID 폭으로 계산)
- 질감 있는 방 (책장, 포스터, 물건이 0.6~4 m에 흩어진 장면)

---

## 1단계 — 폰 앱 설치 + 렌즈 공장값 받기

```bash
./venv/bin/python z_phone_stereo.py --install --list     # 앱이 이미 설치돼 있으면 --install 생략
```

출력에서 `logical 0 ... physical 2 ..., physical 5 ...` 가 보이는지 확인한다.
결과는 `phone_stereo/runs/cameras.json` 에 저장되고, `z_phone_calib.py` 는 이 파일을 기본으로 읽는다.

> 확인: `adb shell getprop ro.product.model` 로 폰 모델을 확인해 둔다. `phone_stereo/runs/cameras.json` 이 없으면 캘리 CLI가 S24 사본(`phone_stereo/cameras_s24.json`)을 대신 읽는다.

## 2단계 — 공장값으로 시작 + 현재 상태 검사

```bash
./venv/bin/python z_phone_calib.py --factory
```

S25 에서의 정상 출력 (2026-10-25 실행):

```
공장값: baseline 16.30mm, 상대회전 0.61°, fx L 255.9 R 426.1 @ [640, 480]
저장: calib_phone_pair.json  scale_status=factory_unverified  phone={'logical': '0', 'physical': ['2', '5']}  image_size=[640, 480]
  ! 공장 회전은 실제 쌍에서 dy 4~6px 남음 — refine 또는 board 필요
  ! yaw/baseline 은 실측 검증 전
```

`!` 두 줄은 오류가 아니다. 공장값은 아직 검증되지 않았다는 안내이고, 3·5단계에서 해결된다. `baseline` 이 15.76mm 로 나오면 S24 인벤토리를 읽은 것이니 1단계(`--list`)를 다시 한다.

출력의 `baseline` 은 S25 기준 16.30 mm, S24 기준 15.76 mm 이다. 이 명령은 `calib_phone_pair.json` 을 공장값(`factory_unverified`)으로 **덮어쓴다**. 이전 파일은 git에 남아 있다.

공장값은 실제 쌍에서 dy가 수 px~수십 px 나므로 그대로 쓰면 안 된다. 다음 단계로 보정한다.

## 3단계 — 장면 쌍으로 회전 보정 (`--refine`)

dy(세로 어긋남)를 0에 가깝게 만드는 단계다. roll·pitch와 광각 초점거리 스케일을 맞춘다.

**촬영** — 폰을 손에 들고 질감 있는 방을 비춘다. 대상은 **0.6 m 이상** 떨어져 있어야 한다. 초점이 1 m로 고정돼 있어서 가까운 물체는 흐려진다.
천천히 방향을 바꿔 가며 20초 동안 촬영한다.

```bash
./venv/bin/python z_phone_stereo.py --physical 2 5 --save-interval 2 --still --duration 30 --out phone_stereo/runs/scene
```

창에 두 렌즈 영상이 보인다. 2초 간격으로, 폰이 정지한 순간만 `captures/<ts>/` 에 저장된다. 6쌍 이상 모이면 된다.

**보정**

```bash
./venv/bin/python z_phone_calib.py --refine phone_stereo/runs/scene
```

합격 기준은 `[refined]` 줄의 각 쌍이 `dy 중앙값 < 1px`, `인라이어 >= 0.7`, `OK` 인 것이다. `dx>0` 비율은 0.9 이상이어야 한다.

- 실패 `대응점이 60개 미만` → 질감이 부족하다. 더 복잡한 장면에서 다시 찍는다.
- 실패 `camera_2.png 가 있는 번들 없음` → 촬영이 안 된 것이다. 촬영 명령의 마지막 오류를 본다. `cannot open camera from background` 는 폰 화면이 꺼졌거나 잠긴 것이다. 촬영 명령은 화면을 켜고 잠금화면을 넘기지만, PIN·패턴 잠금은 직접 풀어야 한다. `adb shell settings put global stay_on_while_plugged_in 2` 로 USB 연결 중 화면이 꺼지지 않게 해 둔다(2026-10-25 S25 에 적용).
- 일부 쌍만 FAIL → 근거리 가림(케이블 등)이나 흔들림 때문이다. 그 `captures/<ts>` 폴더를 지우고 다시 실행한다.

- **6쌍 이상** 필요하다. `--still` 은 정지한 순간만 저장하므로, 방향을 바꿀 때마다 **1초씩 멈춘다**. 30초 동안 계속 움직이면 1장만 저장된다(2026-10-25 실제로 2쌍만 저장됨). 출력 첫 줄 `장면 쌍 N개` 를 확인한다.

결과는 `factory_baseline_refined` 이다. dy는 맞았지만 **거리(스케일·yaw)는 아직 검증되지 않았다.**

> **S25 주의 — `광각 fx 스케일` 이 0.82 근처로 나온다 (S24 는 0.991).** (5단계 렌즈별 보드 캘리로 확인: 초광각 fx **312** (공장 256), 광각 fx **424** (공장 426). 즉 초광각 스트림이 크롭이고 광각은 공장값이 맞다. refine 의 0.82 는 이 차이를 광각 쪽에 잘못 흡수한 값이라, refine 결과의 K 는 5단계의 출발점일 뿐이다.) 공장값은 광각/초광각 배율을 1.665배라고 하지만, 실제 S25 640×480 영상 두 장의 배율은 1.38~1.39배다(2026-10-25 실측, 장면 2개 일치). 스트림이 센서 전체보다 넓을 수는 없으므로, 초광각 스트림이 잘려(크롭) 나오는 것으로 보인다(실제 초광각 fx ≈ 308, 공장값 256). refine 은 이 차이를 광각 fx 를 줄이는 쪽으로 흡수한다. 그래서 dy 는 맞아도 **두 렌즈의 초점거리 절대값은 틀린 상태**다. 5단계에서 `--free-intrinsics` 로 바로잡는다.

## 4단계 — 체커보드 타겟 준비

```bash
./venv/bin/python z_calibrate.py --make-target --screen laptop     # target_laptop.png (1920x1080)
```

1. 체커보드를 띄울 화면에서 `target_laptop.png` 를 **실제 크기(100%) 전체화면**으로 연다. 확대/축소 상태면 안 된다.
2. 화면 위쪽 세로 막대 2개의 **왼쪽 모서리끼리 거리**를 자로 잰다. 이 값(mm)이 `--ruler-mm` 이다.
   - 1920×1080 15.6" 노트북은 약 179 mm 이다. 이전 태블릿에서는 145 mm 였다. 화면마다 다르므로 **반드시 실측**한다.
3. 화면 밝기는 중간 이상으로 올린다.

**자가 없을 때 / 이 PC 화면에 띄울 때:** 화면의 실제 폭(EDID)으로 계산한다. `xrandr | grep " connected"` 에 나오는 mm 폭을 쓴다.
`--ruler-mm = 폭mm / 가로픽셀 × 1000`. 이 노트북(MSI Katana 17, 382 mm / 1920 px)은 **199** 이다. EDID 는 mm 반올림이라 오차 ±0.3% 정도로 무시할 만하다.
이때 보드는 5단계의 `--show-board` 로 띄운다. 이 옵션이 1:1 표시를 확인하고, 1:1 이 아니면 아무것도 저장하지 않는다.

## 5단계 — 보드 촬영 + `stereoCalibrate` (`--board`) → `metric`

**촬영** (960×720으로 찍어 코너 정밀도를 높이고, 저장은 640×480으로 한다):

```bash
# 보드를 다른 화면(태블릿 등)에 띄운 경우
./venv/bin/python z_phone_stereo.py --physical 2 5 --size 960 720 --save-interval 1.5 --still --board-hud --duration 180 --out phone_stereo/runs/board
# 보드를 이 PC 화면에 띄우는 경우 (촬영 창 대신 보드가 전체화면으로 뜨고, 상태가 보드 여백에 표시됨)
./venv/bin/python z_phone_stereo.py --physical 2 5 --size 960 720 --save-interval 1.5 --still --board-hud --show-board target_laptop.png --duration 240 --out phone_stereo/runs/board
```

`--show-board` 화면 읽는 법: **테두리 초록 = 방금 저장**, 빨강 = 보드 안 보임(`NO BOARD in cam 2` = 초광각에서 못 찾음) 또는 움직이는 중, 노랑 = 간격 대기. 아래 글자에 `saved N` 이 나온다. 아래 여백 **왼쪽 작은 화면 = 초광각(2), 오른쪽 = 광각(5)** 실시간 뷰파인더다. 두 화면 모두에 보드 전체(위쪽 막대 포함)가 들어오고 `BOARD OK` 가 떠야 한다. Q 로 종료.

- **거리 35~45 cm.** 이 노트북 보드(350 mm)는 광각 렌즈에 30 cm 이상에서야 다 들어오고, 40 cm 에서 화면의 약 60% 를 채운다. 2026-10-25 실제 시도: 70~80 cm 는 초광각에서 너무 작아 미검출, 15~20 cm 는 두 렌즈 모두 보드가 잘리고 흐림(초점 1 m 고정) → 둘 다 0장.
- **권장: 폰을 고정하고 노트북을 움직인다.** 폰을 책 더미·컵 등에 기대 40 cm 앞에 세워 두고, 노트북을 책상 위에서 돌리고(좌우 기울기), 화면 각도를 바꾸고(상하 기울기), 옆으로 밀어(화면 속 위치) 자세를 바꾼다. 손을 떼면 바로 정지라 저장이 잘 된다.
- 손으로 들 때는 위치마다 **팔꿈치를 책상에 대고 2초 멈춘다.** 3분 동안 한 번도 정지 판정(프레임 차 < 1.5, 자이로 < 0.05 rad/s)을 못 받으면 0장이 된다(첫 시도에서 실제로 그랬다).

- 화면에 렌즈별로 `BOARD OK`/`NO BOARD` 가 표시되고, 아래에는 저장 상태(`MOVING`, `SAME VIEW`, `WAIT`, `SAVED #n`)가 뜬다.
- **보드 화면과 폰 둘 다 정지**해야 한다. 두 렌즈는 노출 시각이 달라서, 움직이는 중에 찍힌 쌍은 좌우가 다른 순간을 담는다.
  폰을 거치대나 책에 기대 놓고 보드를 옮기거나, 보드를 세워 두고 폰을 옮긴다. 손을 떼고 1초 기다리면 `SAVED` 가 뜬다. 그다음 위치로 옮긴다.
- 보드가 화면의 위·아래·좌·우·모서리에 오게 하고, 좌우·상하로 20~40° 기울인 자세를 섞는다. **20장 이상** 모은다.
- 두 렌즈 모두에 보드가 통째로 보여야 한다. 광각(5) 화면이 좁으므로 그쪽 기준으로 맞춘다.

**보정**

```bash
./venv/bin/python z_phone_calib.py --board phone_stereo/runs/board --screen laptop --ruler-mm <4단계 실측> \
    --size 960 720 --target-size 640 480 --base calib_phone_pair.json --free-intrinsics
```

- **S25 는 `--free-intrinsics` 필수.** 이 옵션은 두 렌즈의 K·왜곡을 **렌즈별로 보드만으로 따로 캘리**(calibrateCamera)한 뒤 고정하고, 두 렌즈 사이 R·T 만 푼다(뷰 20장 이상, `z_calibrate.py --run-stereo` 와 같은 순서). 처음 구현은 refine K 를 초기값으로 K·R·T 를 한꺼번에 풀었는데, S25 실데이터에서 틀린 해(fx 258/349, baseline 19.75 mm, RMS 0.35)로 수렴해 baseline 게이트에 걸렸다 — 2026-10-25 수정. 합성 검증(초광각 공장 fx 가 실제의 1/1.2인 경우):

  | 방식 | 추정 fx (참 307/423) | 0.80 m 판 거리 | 판정 |
  |---|---|---|---|
  | K 고정(옵션 없음) | 256/353 | 0.676 m (−15.3%) | RMS 0.90 px 로 통과하던 것을 **이제 `board_unreliable` 로 거부** (2026-10-25 게이트 추가) |
  | `--free-intrinsics` | 307/423 | 0.802 m (+0.2%) | RMS 0.17 px, `metric` |

  옵션 없이 돌리면 1 px 게이트는 겨우 통과하지만 거리가 15% 틀린다. 그래서 `--base` 의 광각 fx 스케일이 1에서 5% 넘게 벗어났는데 `--free-intrinsics` 가 없으면 `board_unreliable` 로 거부하고 `calib_phone_pair.json` 을 덮어쓰지 않는다. S24 처럼 0.99 근처면 K 고정도 그대로 허용한다.

- `--base calib_phone_pair.json` 은 **3단계에서 이 폰으로 만든 refine 결과**다. 이 파일의 K(광각 fx 스케일 포함)는 고정값으로, R·T는 초기값으로 쓰인다. 다른 폰이 만든 파일이면 공장 baseline 비교에서 거부된다. 3단계를 건너뛰었다면 `--base` 를 빼고 실행한다(공장 K를 고정값으로 사용).
- 통과 조건은 RMS ≤ 1 px, 뷰 ≥ 8, baseline 이 공장값의 ±15% 이내다. 통과하면 `scale_status=metric` 으로 저장된다.
- 하나라도 실패하면 `board_unreliable` 이 된다. 이때는 `calib_phone_pair.json` 을 **덮어쓰지 않고** `calib_phone_pair.unreliable.json` 에만 이유와 함께 저장한다.

| 출력 | 의미 / 대응 |
|---|---|
| `동기 불일치로 제외 N쌍` | 움직이는 중에 찍힌 쌍을 자동으로 뺀 것이다. 많으면 더 오래 정지해서 다시 찍는다. |
| `RMS > 1px` | 보드가 움직였거나, 화면 반사·흐림이 있다. `뷰별 오차 최악 3` 에 나온 폴더를 지우고 다시 실행한다. |
| `baseline 이 공장값과 xx% 차이` | `--ruler-mm` 오기입이나 화면 배율(100%가 아님)을 먼저 의심한다. |
| `쓸 수 있는 쌍 N개` | 코너 미검출이 많은 것이다. 보드를 더 크게(가깝게), 밝게 해서 다시 찍는다. |

### S25 실제 결과 (2026-10-25)

| 항목 | 값 |
|---|---|
| 3단계 refine | 장면 7쌍 전부 OK (dy 0.30~0.72 px), 광각 스케일 0.822 |
| 5단계 촬영 | 폰을 40 cm 앞에 고정, 노트북을 움직여 `--show-board` 로 39뷰 (`--ruler-mm 199`, EDID) |
| 렌즈별 단독 캘리 | RMS 0.083 / 0.082 px, fx@640 초광각 312.1 / 광각 423.5 |
| stereoCalibrate | RMS 0.105 px, baseline **16.64 mm** (공장 16.30, +2.1%), 상대회전 0.66°, `metric` |
| 정류 확인 (장면 7쌍) | dy 0.25~0.55 px, 전부 OK |
| 거리 확인 (자 없이) | 보드 13뷰 0.40~0.60 m: FFS 깊이 vs 보드 PnP 거리 중앙값 **+0.8%**, 최대 1.1% |

거리 확인은 같은 보드·같은 `--ruler-mm` 에 기대므로 완전히 독립은 아니다(화면 폭 EDID 가 틀리면 둘 다 같이 틀린다). 크기를 아는 물체 하나(A4 297 mm, 카드 85.6 mm 등)로 아래 6-2 를 하면 독립 확인이 된다.
refine 결과 사본: `phone_stereo/runs/calib_s25_refine.json` (5단계 재실행 시 `--base` 로 사용).

## 6단계 — 검증 (실측 1개)

1. **정류 확인** — 보정에 쓰지 않은 새 장면 번들로 확인한다:
   ```bash
   ./venv/bin/python z_phone_stereo.py --physical 2 5 --save-interval 2 --still --duration 10 --out phone_stereo/runs/verify
   ./venv/bin/python z_phone_calib.py --check phone_stereo/runs/verify
   ```
   모든 쌍이 `OK` (dy 중앙값 < 1 px) 여야 한다.

2. **절대거리 확인** — 질감 있는 물체(책, 상자)를 렌즈에서 자로 잰 거리(0.5~1 m)에 놓고 번들을 저장한 뒤, FFS로 깊이를 낸다:
   ```bash
   ./venv/bin/python z_phone_stereo.py --physical 2 5 --headless --duration 4 --out phone_stereo/runs/known
   ./venv_ffs/bin/python z_phone_stereo.py --physical 2 5 --calib-stereo calib_phone_pair.json --yolo seg --offline phone_stereo/runs/known
   ```
   `phone_stereo/runs/known/depth.json` 에 있는 해당 객체의 `dist_m` 을 자로 잰 값과 비교한다. 1 m에서 ±5% 정도가 이 baseline(약 16 mm)의 정상 범위다.
   YOLO가 물체를 못 잡으면 `depth_seg.png` 의 깊이 색으로 확인한다.

3. 라이브 실행 (README 명령). 처음 몇 초는 0.6 m 이상 떨어진 질감 있는 물체에 대고 정지한다 — 정지한 쌍 3개로 정류 검사가 끝난다:
   ```bash
   ./venv_ffs/bin/python z_phone_stereo.py --physical 2 5 --calib-stereo calib_phone_pair.json --yolo seg --rgbd-viewer --out phone_stereo/runs/my_view
   ```

### 보드가 없을 때의 대안 — 실측 거리 1개로 yaw 고정 (`--known`)

3단계 후 5단계 대신 사용한다. 정확도는 보드보다 낮다(baseline은 공장값 그대로 둔다).

```bash
./venv/bin/python z_phone_calib.py --known phone_stereo/runs/known --known-m 0.80 --roi 220 150 200 180
```

ROI 는 **정류된 초광각(왼쪽) 영상**의 물체 영역(x y w h)이다. 결과는 `known_distance_pinned` 다.

---

## 부록 A — 노트북 웹캠 단일 캘리 (1·2세대 경로용, `calib.json`)

폰 depth만 쓴다면 필요 없다. 저장소의 `calib.json` 은 이전 노트북(HP 웹캠)의 값이다.

```bash
./venv/bin/python z_calibrate.py --make-target                    # target_s24.png → 폰 화면에 가로로 전체화면, 막대 실측
./venv/bin/python z_calibrate.py --capture --index 0              # 보드가 FOUND 일 때 SPACE, 각도·위치 바꿔 15~20장
./venv/bin/python z_calibrate.py --run --ruler-mm <실측>          # 게이트: RMS<1px, 뷰>=15, 커버리지>=12/16
```

- 웹캠은 1280×720 MJPG를 지원해야 한다(`lib_cam.SIZE`). 지원하지 않으면 `해상도 설정 실패` 로 즉시 멈춘다.
- 카메라 2대: `--capture-stereo --index-l 0 --index-r 2` → `--run-stereo --ruler-mm <실측>` → `calib_stereo.json`. T의 x 성분이 음수여야 한다.

---

## 검증 기록 (2026-10-22 합성 검증 / 2026-10-25 S25 실제 캘리 — 이 문서를 실제로 따라 실행)

환경: Galaxy S25 SM-S931N (USB 연결), RTX 4050 Laptop, venv(py3.12, opencv 4.13), venv_ffs(torch 2.6+cu124).

### 실기기에서 실행한 것

| 단계 | 명령 | 결과 |
|---|---|---|
| 1 | `z_phone_stereo.py --list` | OK. logical 0 / physical 2·5·6. `phone_stereo/runs/cameras.json` 생성 (아래 수정 1 이후) |
| 2 | `z_phone_calib.py --factory` | OK. baseline 16.30 mm, 상대회전 0.61°, fx 255.9 / 426.1 @640×480 |
| — | 기존 S24 `calib_phone_pair.json` 을 S25 쌍으로 `--check` | **FAIL**: dy 중앙값 27.4 px. 이 폰에서 다시 캘리해야 함을 확인 |
| 3·5 촬영 | `--size 960 720 --save-interval 1.5 --still --board-hud` | 스트림·HUD·저장 게이트 동작 확인(99쌍/8초, 예외 없음). 폰이 엎어져 있어 보드·장면 데이터는 없음 |

### 손이 필요한 단계 → 합성 데이터로 검증

실제 장면과 보드 촬영은 사람이 해야 한다. 그래서 **이 S25의 공장 K·왜곡**을 그대로 쓰고, 알려진 "참" 포즈로 번들을 렌더했다. 참 포즈는 공장 대비 회전 오차 (0.20°, 0.30°, −0.15°), baseline 16.00 mm, 광각 fx −0.8% 이다. 렌더는 왜곡 포함 광선-평면 교점 방식이고, 스크립트는 세션 scratchpad의 `synth_phone.py` 다.
이 번들에 3·5·6단계 명령을 그대로 실행했다.

| 단계 | 결과 | 참값 |
|---|---|---|
| 3 `--refine` (8쌍) | dy 1.0~2.2 px → **0.15~0.29 px**, 전부 OK. 광각 스케일 0.9922 | 0.992 |
| 5 `--board` (26쌍, 960→640) | RMS 0.174 px, 뷰 26, baseline **16.04 mm**, `metric` | 16.00 mm |
| 5 결과 vs 참값 | 회전 오차 (−0.013°, 0.005°, 0.000°), 광각 fx 422.73 | fx 422.65 |
| 6 `--check` (보정에 안 쓴 4쌍) | dy 0.09~0.10 px, 전부 OK | |
| 6 FFS `--offline` | 실행 OK (dy 0.10 px, `metric`) | |
| 0.80 m 판 FFS 깊이 | **metric 0.797 m (−0.33%)** · `--known` 0.817 m (+2.1%) · refine만 1.105 m (**+38%**) | 0.800 m |
| `--known` 대안 | yaw 보정 +0.298° | +0.30° |
| 부록 A `z_calibrate.py --run` (합성 18장) | RMS 0.162 px, 커버리지 15/16, cx·cy 오차 < 0.7 px, PASS | |
| `z_selftest.py` / 폰 unittest | 31/31 PASS / 16 OK (수정 후 재실행) | |

refine 만으로는 yaw 가 공장값에 머문다. 그래서 거리가 38% 틀렸다. **5단계(또는 `--known`)를 생략하면 안 된다.**

### 실행 중 발견해서 고친 오류

| # | 증상 | 원인 | 수정 |
|---|---|---|---|
| 1 | 새 폰에서 `--factory` 를 실행하면 S24 공장값이 들어감 | `--list` 는 `runs/<시각>/cameras.json` 에 저장하는데, 캘리 기본 인벤토리는 `runs/cameras.json` 을 찾고 없으면 S24 사본을 사용 | `z_phone_stereo.py --list` 가 `phone_stereo/runs/cameras.json` 에도 저장 |
| 2 | 문서의 `--base calib_phone_pair.json` 이 다른 폰 파일이어도 통과 | 물리 id(2,5)만 비교 — 기종이 달라도 같음 | `z_phone_calib.py`: base 의 공장 baseline 이 현재 인벤토리와 1% 넘게 다르면 거부 |
| 3 | `z_phone_calib.py` import 실패 (`No module named 'open3d'`) | venv 에 open3d 미설치 | `./venv/bin/pip install open3d==0.20.0 loguru==0.7.3` |
| 4 | 저장 게이트가 `WAIT 0.7s`, `0.6s` … 줄마다 출력 | 중복 판정 키에 남은 초가 포함 | 숫자를 지운 키로 비교 |
| 5 | refine/known 경고가 S25 에서도 "baseline 15.76mm" 출력 | 문자열 하드코딩 | 실제 공장 baseline 값으로 출력 |
| 6 | K 고정 보드 캘리가 RMS 0.90 px 로 `metric` 통과, 거리 −15% (합성) | refine 이 초광각 크롭을 광각 fx 0.82 로 흡수 | `--free-intrinsics` 없이 refine 광각 스케일 편차 > 5% 면 `board_unreliable` |
| 7 | 촬영 `cannot open camera from background` | 화면 꺼진 폰에서 앱이 뒤에서 시작 | 시작 전 `KEYCODE_WAKEUP` + `wm dismiss-keyguard`, 원인 안내 메시지, 폰 `stay_on_while_plugged_in 2` |
| 8 | 보드 촬영 0장 (3회) | 손떨림·거리(70~80 / 15~20 cm)·보드가 화면을 덮어 상태 안 보임 | `--show-board`(1:1 확인·재요청, 상태 테두리, 두 렌즈 뷰파인더), 폰 고정 + 노트북 이동 절차 |
| 9 | `--free-intrinsics` 가 baseline 19.75 mm(+21%) 로 수렴 | refine K 초기값에서 K·R·T 공동 추정이 틀린 해로 감 | 렌즈별 `calibrateCamera` 후 R·T 만 (`z_calibrate.py --run-stereo` 와 같은 순서) → 16.64 mm |
| 10 | 라이브 `Phone rectification failed` (dy 1.06 / [0.60, 4.77, 2.59] px) | 흔들린 한 쌍으로 판정 | 정지한 질감 쌍 3개 중앙값 (`motion_px` ≥ 1 px 인 쌍 제외) |
| 11 | 자이로 동기 보상이 항상 0° | 노출 차(~6 ms) 안의 자이로 표본만 적분(주기 ~10 ms) | 표본 구간과의 겹침 적분 (실데이터 1.094°) |

### 남은 것

2026-10-25 에 S25 로 1~5단계와 6단계 정류·거리 확인(보드 PnP 대비 +0.8%)을 마쳤다. 남은 선택 사항은 크기를 아는 물체(A4, 카드 등)로 하는 독립 거리 확인 하나다.
