# 스마트폰 후면 카메라 → USB → PC

처음 Galaxy S24 SM-S921N / Android 16에서 만들고 확인한 구성이다. **현재 사용하는 폰은 Galaxy S25 SM-S931N** 이며, 같은 물리 렌즈 ID(2=초광각, 5=광각, 6=망원)로 2개 스트림 수신·640×480/960×720 을 확인했다(2026-10-22). 아래 표의 수치는 S24 측정값이다. 휴대전화에 설치하는 `Phone Stereo` 앱은 Camera2의 logical camera 하나에 물리 출력 2~3개를 연결한다. PC는 ADB USB 포워딩으로 원본 YUV(NV21)를 받아 표시하고 NVIDIA GPU에서 YOLO를 실행한다.

## 실행

USB 디버깅을 허용한 폰을 연결하고 저장소 루트에서 실행한다. 카메라를 점유하는 기존 `tools/phonecam.sh`/scrcpy 실행은 먼저 종료한다. 기본 후면 렌즈 ID는 이번 S24에서 확인한 값이며, 다른 기기는 `--list`로 조회해야 한다.

```bash
# 최초 설치 또는 Android 앱 소스 변경 후 빌드·재설치 및 렌즈 조회
./venv/bin/python z_phone_stereo.py --install --list

# 기본: 광각 5 + 초광각 2, 640×480, 30 FPS 요청, PC에서 seg + bbox 표시
./venv/bin/python z_phone_stereo.py --fps 30 --yolo both

# bbox 전용 YOLO 모델
./venv/bin/python z_phone_stereo.py --fps 30 --yolo bbox

# 세 렌즈 동시 표시: 광각 5 + 초광각 2 + 망원 6
./venv/bin/python z_phone_stereo.py --physical 5 2 6 --yolo both

# 시간 제한 검증, 화면 표시 없이 프레임 통계 저장
./venv/bin/python z_phone_stereo.py --headless --duration 20
```

폰의 앱 화면은 켜두어야 한다. USB 전송용 포트는 폰과 PC의 loopback 8765이며 외부 네트워크에 카메라를 공개하지 않는다. `Q`/`Esc`/`Ctrl-C`로 종료하면 이 앱의 카메라와 ADB 포워딩을 해제한다. `S`는 타임스탬프가 맞는 원본 PNG 묶음을 `phone_stereo/runs/<실행시각>/captures/`에 저장한다. 종료 시 마지막 묶음과 `summary.json`도 실행 디렉터리에 저장한다.

기본 미리보기는 센서 출력 방향 그대로이며 회전·리사이즈하지 않는다. 추론 결과는 별도 창의 **추론에 사용된 프레임**에 그린다. 느린 추론 결과를 현재 라이브 프레임 위에 잘못 겹치지 않는다. `--yolo both`는 segmentation 모델 한 번에서 나온 mask와 bbox를 함께 표시하며, `--yolo bbox`는 detection 모델을 사용한다.

## 직접 확인한 결과

| 구성 | 조건 | 결과 |
|---|---|---|
| 광각 5 + 초광각 2 | 640×480, 15 FPS, 15초 | 각각 217프레임, 217쌍, 약 15 FPS |
| 광각 5 + 초광각 2 + 망원 6 | 640×480, 15 FPS, 12초 | 각각 171/172/171프레임, 171묶음, 약 15 FPS |
| 두 렌즈 + PC GUI + YOLO seg/bbox | 640×480, 30 FPS, 25초 | 736/737프레임, 735쌍, 약 30 FPS, `cuda:0` 추론 확인 |
| 두 렌즈 + bbox 전용 모델 | 640×480, 30 FPS, 20초, `venv_ffs` | 582쌍, GPU 추론 447회, 중앙값 11.26ms |

두 렌즈+YOLO 시험의 마지막 추론은 약 16.7ms였다. 전체 평균이나 FFS 포함 시간은 아니다. 수신 이미지들은 서로 다른 픽셀 배열이며 렌즈별 화각을 갖는다. 위 검증은 단기 실행이며 장시간 발열·배터리·고해상도 성능을 보증하지 않는다.

관측된 Image timestamp 차이는 0ms지만 HAL의 sensor sync 등급은 `APPROXIMATE`다. 동일한 보고 timestamp가 정밀한 물리 노출 동기화를 입증하지는 않는다. 다른 시점 프레임을 재사용하지 않으며 CLI 기본 35ms 허용차를 넘으면 묶음에서 제외한다. `--max-skew-ms`로 변경할 수 있다.

## FFS 객체 depth

`--calib-stereo`를 주면 PC FFS 추론을 활성화하고 기존 `lib_ffs`, `lib_rectify`, `z_object_depth`의 seg/bbox 집계 코드를 재사용한다. FFS는 앞의 두 렌즈만 사용한다. 실행 환경은 `venv_ffs`다.

```bash
./venv_ffs/bin/python z_phone_stereo.py --yolo both \
  --calib-stereo calib_phone_pair.json --iters 4
```

보정 파일 `calib_phone_pair.json` 은 `z_phone_calib.py` 가 만든다. **현재 파일은 S25 용 `metric` (2026-10-25: 보드 39뷰, RMS 0.105 px, baseline 16.64 mm, FFS vs 보드 PnP 거리 +0.8%)** 이다. 절차와 결과: [doc_CALIBRATION.md](../doc_CALIBRATION.md). 출처 단계는 다음과 같다.

| 단계 | 명령 | `scale_status` | 의미 |
|---|---|---|---|
| 공장값 | `./venv/bin/python z_phone_calib.py --factory` | `factory_unverified` | Camera2 공장 포즈 그대로. 실쌍에서 정류 dy 2~5px → 쓰지 말 것 |
| 회전 보정 | `./venv/bin/python z_phone_calib.py --refine phone_stereo/runs/<번들…>` | `factory_baseline_refined` | 장면 SIFT 대응점으로 roll/pitch + 광각 fx 스케일 보정(yaw 공장 고정). dy 는 맞지만 yaw 편향으로 거리가 11 % 짧았다 |
| 실측 1개 | `./venv/bin/python z_phone_calib.py --known <번들> --known-m <m> --roi x y w h` | `known_distance_pinned` | 거리를 아는 물체의 ROI 시차로 yaw 고정. 보드 없을 때 대안 |
| 체커보드 | `./venv/bin/python z_phone_calib.py --board phone_stereo/runs/<보드 번들> --screen laptop --ruler-mm <실측> --size 960 720 --target-size 640 480 --base <이 폰의 refine 결과> --free-intrinsics` | `metric` (rms≤1px, 뷰≥8, baseline 공장값 ±15%; refine 광각 스케일이 1에서 5% 넘게 벗어났는데 `--free-intrinsics` 가 없으면 거부) | S25: 렌즈별 단독 캘리(fx 312/424) 후 R·T, RMS 0.105 px, 39뷰, baseline 16.64 mm. S24(2026-09-22): RMS 0.26 px, baseline 15.53 mm, FFS 오차 −1.8 %. 촬영은 `--still --board-hud` (+ PC 화면에 띄울 땐 `--show-board`) |

**초점은 고정해야 한다.** 광각 5 는 AF 렌즈라 자동초점이면 초점거리가 프레임마다 0.3~0.7% 변해 정류가 1~2px 씩 흔들린다. 앱은 기본으로 `CONTROL_AF_MODE_OFF` + `LENS_FOCUS_DISTANCE` 1 m 로 고정하며(`--focus-m`, 0 이면 자동초점), 캘리 번들의 초점값이 json 에 기록되고 실행값과 다르면 객체마다 `focus_mismatch` 경고가 붙는다. 초광각 2 는 고정초점이다.

공장값 변환 규약(NDK 문서 인용은 `lib_phone_calib.py` 머리): `X_B = R_B R_Aᵀ X_A + R_B(t_A − t_B)`, K 는 active array→출력 해상도 비례, 왜곡은 `[κ1,κ2,κ4,κ5,κ3]`. 초광각 2 가 왼쪽, 광각 5 가 오른쪽(Tx = −15.76mm)이라 파일의 `phone.physical` 은 `["2","5"]` 다. `--physical 5 2` 로 받아도 수신기가 같은 두 렌즈를 확인한 뒤 순서를 뒤집어 쓴다. 다른 렌즈(6)나 다른 해상도는 거부한다.

```bash
# 저장 번들로 depth 만 (폰 불필요): 번들 폴더에 depth_both.png / depth.json 생성
./venv_ffs/bin/python z_phone_stereo.py --physical 2 5 --calib-stereo calib_phone_pair.json --yolo both \
  --offline phone_stereo/runs/probe_now
# 라이브 FFS + seg/bbox
./venv_ffs/bin/python z_phone_stereo.py --physical 2 5 --calib-stereo calib_phone_pair.json --yolo both
```

S24 기록 (RTX 4060, venv_ffs, 640×480, 초점 1 m 고정): 오프라인 — 사람 seg 0.395/0.412 m (bbox 는 사람이 화면 대부분이라 배경 혼입 → seg 를 볼 것). 라이브 25초 — 367쌍 15.0 fps, FFS+YOLO(seg+bbox) 80회, 중앙값 258 ms, 첫 쌍 dy 0.32px·인라이어 0.95, 벽시계 1.80 m·183×60 mm.

**HAL의 동기 등급은 `APPROXIMATE`**이므로 동일한 논리 timestamp만으로 동시 노출을 보장할 수 없다. 앱은 `Image.getTimestamp()`와 **정확히 같은 논리 `SENSOR_TIMESTAMP`**의 촬영 결과를 찾아, 해당 렌즈의 물리 `SENSOR_TIMESTAMP`를 전송한다. 이미지/결과 콜백은 어느 쪽이 먼저 와도 연결하며, 결과 또는 물리 timestamp가 없으면 이전 오프셋을 재사용하지 않는다. 대기 항목은 24개/1초로 제한한다. Android `RESULT` 로그의 `matched`, `unmatched_dropped`로 연결 및 대기 이미지 폐기 수를 확인한다.

PC는 첫 렌즈 프레임 시각을 기준으로 다른 렌즈의 앞뒤 후보가 도착할 때까지 기다린 뒤 가까운 후보를 선택한다(보통 최대 한 프레임의 추가 대기). 선택한 묶음의 최대 시각차가 `--max-skew-ms 35`를 넘으면 제외하고 프레임을 재사용하지 않는다. `--raw-ts`는 논리 timestamp를 그대로 보내는 비교용 옵션이다. 이 변경은 메타데이터 연결과 프레임 선택을 바로잡으며, 센서 노출 자체를 동기화하지 않는다. 빠른 물체 운동과 롤링셔터 오차는 남을 수 있다.

이전 구현의 중앙값 6ms / p95 14ms는 **최신 오프셋을 재사용하던 코드의 과거 측정치**다. 새 구현의 결과로 해석하지 않는다. `frame_timing` 센서값(물리별 오프셋 ms, 노출, 프레임 주기, 롤링셔터 skew)은 계속 `summary.json`/`pair.json`에 기록된다. 캘리 촬영은 `--still --board-hud`로 정지 순간을 사용한다.

연결 로직 회귀 테스트: `./venv/bin/python -m unittest phone_stereo.test_receiver phone_stereo.test_timestamp_matcher` (Java 테스트에 JDK 필요).

**두 렌즈 노출 시각이 같게 보고될 때** (`pair.json` 의 `timestamp_ns` 두 값이 같고 앱 로그 `RESULT … phys2=0 phys5=0`, depth 보고서 `lens_timing: "unknown"`): S25 를 재시작한 뒤 폰의 카메라 HAL 이 이렇게 보고했다(2026-11-05, 재시작 이전엔 5~28 ms 차이를 보고). **실제 노출은 여전히 70~78 ms 어긋나 있어서** 폰을 움직이면 좌우 영상이 서로 다른 순간이 돼 세로 어긋남이 생긴다(자이로 0.128 rad/s 에 dy 4.40 px = 0.128 × 0.078 s × 438 px). 이때는 HAL 값 대신 **영상 + 자이로로 노출 차 Δt 를 추정해 보상**한다 (`lib_phone_depth.estimate_lens_offset`): 렌즈 사이 회전을 `R·Rg(Δt)` 로 두고 대응점 Sampson 오차를 Δt(±100 ms)에 대해 최소화. 실제로 실패한 쌍: Δt 72 ms 추정, dy 4.40 → 0.49 px, 인라이어 1% → 92%. 보고서 `lens_offset_ms`·`lens_offset_estimated`.
  - 영상 가로축·광축 둘레 각속도가 0.05 rad/s 이상일 때만 새로 추정하고(세로축 yaw 는 dy 를 만들지 않아 관측 불가), 그 외엔 직전 추정을 이어 쓴다. 노출 차는 천천히 변한다(초당 ~4 ms).
  - 한계: 회전만 보상한다(평행이동은 못 함 — 가까운 물체를 빠르게 옮기면 남는다). 처음 추정 전에는 최악 차(프레임 주기 66.7 ms)로 움직임을 계산하므로 **시작 몇 초는 폰을 가만히** 들어야 한다. 차를 추정한 뒤에도 자이로 창의 뒤쪽 표본이 늦게 도착하면 보상이 조금 모자랄 수 있다.

**라이브 정류 검사**: depth 를 내기 전, 질감 있고 **정지한** 쌍 3개의 dy 중앙값이 1 px 미만인지 본다(그 전엔 객체에 `rectification_unverified`). 노출+롤링셔터 동안 회전으로 상이 1 px 이상 움직인 쌍은 세지 않는다(보고서 `motion_px`). 두 렌즈 노출 차 동안의 회전은 자이로로 보정한다(보고서 `gyro_skew_compensation_deg`). 다른 폰의 캘리는 dy 20 px 이상이라 `Phone rectification failed` 로 멈춘다.
**알려진 약점**: 천장 타일 같은 **반복 무늬**를 보면 SIFT 가 엉뚱한 곳끼리 짝지어 정지한 쌍도 dy 가 크게 나올 수 있다(2026-11-05 천장을 보던 폰: 판정 쌍 dy 17.8 px, 저장된 쌍은 대응점 1개). 대응점 수로 거르면 칼리브레이션이 틀린 경우(대응점 ~20개)도 같이 걸러져 고치지 않았다. 판정은 **질감이 다양한 장면**(방 전경, 책상 위 물건)을 0.6 m 이상 떨어져 비출 때 믿을 수 있다. S25 실측 라이브: 289초, 추론 687회 중앙값 239 ms(RTX 4050), 판정 dy 0.31 px.


**거리 정확도 한계**: baseline 은 S25 공장값 16.30 mm(S24 15.76 mm), 정류 후 f ≈ 438 px 라 1 m 에서 시차가 7.1 px 뿐이다. 시차 0.5px 오차 → 깊이 오차 ≈ Z²×0.070 (0.5 m 18 mm, 1 m 70 mm, 2 m 0.28 m). 캘리 yaw 0.1° 오차는 시차 0.76px 편향 = 1 m 에서 11%. `metric` 이 아닌 상태의 결과에는 객체마다 `scale_not_validated:<status>` 경고가 붙는다.

## 객체 회전 (yaw / pitch / roll)

RGB 화면의 객체 라벨 아래 줄(노란 글자)에 카메라 기준 회전이 뜬다: `yaw +20 pitch -3 roll +12` (도). `depth.json` 객체의 `rotation` 에도 같은 값(+ `tilt_deg`, 법선 `normal_cam1`)이 들어간다.

| 값 | 뜻 | 부호 |
|---|---|---|
| yaw | 보이는 면이 좌우로 얼마나 돌아섰나 | **+ = 면의 오른쪽 끝이 더 멀다**, − = 왼쪽 끝이 더 멀다 |
| pitch | 위아래로 얼마나 기울었나 | **+ = 위쪽이 더 멀다**(뒤로 젖힘), − = 아래쪽이 더 멀다 |
| roll | 면 안에서 긴 변이 가로에서 얼마나 돌아갔나 | **+ = 영상에서 시계 방향**. `~` 가 붙으면 정사각에 가까워 긴 변이 불안정해 ±45° 로 접은 값, `--` 이면 면이 바닥·천장 방향이라 정의 안 됨 |
| tilt (json 만) | 면과 영상 평면 사이 각 (0 = 정면) | |

정면으로 마주 보면 `yaw 0 pitch 0`. 카메라 좌표계(왼쪽 렌즈 원 좌표) 기준이라 폰을 기울이면 값이 같이 바뀐다 (중력 기준이 필요하면 `center_world_m` 처럼 IMU 로 바꿔야 한다 — 미구현).

- **계산**: 마스크 안 화소의 정류 시차를 평면 `d = A·u + B·v + C` 로 최소제곱 적합 → 법선 `n ∝ (A, B, (C + A·cx + B·cy)/f)` → `R1ᵀ` 로 원 카메라 좌표 (`lib_rectify.fit_plane_disparity`, 정의 `lib_stereo.plane_orientation`). 3D 점에 SVD 를 쓰면 깊이 노이즈에서 법선이 시선 쪽으로 치우쳐(합성 20° 판, 노이즈 2% 에서 +2.6°) 시차 평면을 쓴다.
- **전제**: 보이는 면이 **하나의 평면**일 때만 계산한다 (`planar_ok`). 병·구·여러 면이 보이는 물체는 `rotation: null`(화면에 회전 줄 없음). 크기가 `non_planar` 인 객체가 그렇다.
- **정확도 (측정)**: S25 보드 39장(0.39~0.65 m, 기울기 3~26°), 스테레오 vs `solvePnP` — pitch 평균오차 0.5°(최대 1.3°), roll 0.3°(0.9°), yaw 1.7°(최대 4.7°, 약 −1.4° 치우침), tilt 1.1°. 보드(35 cm 폭)처럼 큰 물체 기준이다. **작은 물체·먼 거리에서는 시차 오차가 상대적으로 커져 더 틀린다** (측정 안 함). 이 범위 밖(기울기 > 26°)은 검증하지 못했다.

## 폰 센서 (IMU·기압)

앱이 자이로·중력·선가속도·게임 회전벡터·회전벡터(125 Hz), 기압(12.5 Hz)을 같은 소켓으로 보낸다(magic `SENS`, payload float32). 카메라와 같은 elapsedRealtimeNanos 시계라 프레임 시각의 센서값을 찍어 `pair.json`의 `imu` 와 depth 보고서 `imu`/`imu_raw` 에 넣는다. `summary.json` 의 `imu` 에 센서별 표본수·주기, `clock_gap_ms` 에 시계 일치 확인값이 있다.

- **중력 정렬**: 객체 `center_world_m` (x 카메라 오른쪽 수평, y 수평 전방, z 위), `height_rel_camera_m`, 보고서 `imu.pitch_deg/roll_deg`.
- **이동 스테레오** (`z_phone_motion.py`): GUI 에서 `S` 로 A 저장 → 폰을 10~20 cm 옆으로 옮겨 정지 → `S` 로 B 저장(10초 안에) → `./venv/bin/python z_phone_motion.py --a <A> --b <B>` (회전은 회전벡터, 이동방향은 영상, 크기는 두 렌즈(약 16 mm) 스테레오, 가속도 적분은 교차검증. 폰을 제자리에서 돌리기만 하면 `스케일을 줄 수 있는 대응점 N개` 로 거부된다). `--dense` (venv_ffs) 면 이동 쌍을 정류해 FFS+seg 를 돌린다. 정지 상태 두 번들은 `baseline_unreliable` 로 거부된다.
- IMU 는 두 렌즈 사이 기하(yaw·baseline)를 관측하지 못한다 — 그건 `--known`/`--board` 의 몫이다.

## 파일과 검증

- `phone_stereo/android/src/com/camera/dualstream/MainActivity.java`: Camera2 촬영·물리 ID 조회·NV21 전송.
- `phone_stereo/build_android.py`: Google Android SDK 35 플랫폼과 build-tools 35.0.0의 고정 다운로드/체크섬 검증, Java APK 빌드. 다운로드 도구와 개발 서명 키는 Git에 저장하지 않는다.
- `lib_phone_stereo.py`: 분할 TCP 패킷 처리·타임스탬프 pairing·수신 통계.
- `z_phone_stereo.py`: 설치·시작(폰 화면 깨우기 포함)·PC 표시·GPU 추론·원본 저장·종료. 캘리 촬영용 `--save-interval --still --board-hud`, PC 화면 보드 표시 `--show-board`(1:1 확인, 저장 상태·두 렌즈 뷰파인더를 여백에 표시).
- `lib_phone_depth.py`: 폰 쌍의 보정값 검증 및 기존 FFS depth 파이프라인 연결.
- `lib_phone_calib.py` / `z_phone_calib.py`: 공장 CameraCharacteristics → OpenCV 스테레오 캘리, 장면 회전 보정, 체커보드 stereoCalibrate, `--known`, `--check`.
- `lib_phone_motion.py` / `z_phone_motion.py`: 회전벡터 + 영상 + 스테레오 스케일로 폰 이동 두 시점을 넓은 baseline 스테레오로.
- `phone_stereo/cameras_s24.json`: 이전 S24 의 `--list` 결과 사본. 현재 폰(S25)의 공장값은 `--list` 가 `phone_stereo/runs/cameras.json` 에 저장하고, `z_phone_calib.py` 가 그 파일을 우선 읽는다.
- `phone_stereo/test_receiver.py`: 잘린/손상된 패킷, 프레임 누락·재사용 방지, 다른 카메라 보정값 거부 테스트.
- `phone_stereo/test_phone_depth.py`: 라이브 정류 판정(질감 없는 쌍·움직이는 쌍 제외, 3쌍 중앙값, 틀린 캘리 거부, 오프라인 1쌍) 테스트.

```bash
./venv/bin/python -m unittest discover -s phone_stereo -p 'test_*.py' -v
```

구현 근거: [Android Camera2 multi-camera](https://developer.android.com/media/camera/camera2/multi-camera), [Image.Plane stride](https://developer.android.com/reference/android/media/Image.Plane), [Image timestamp](https://developer.android.com/reference/android/media/Image#getTimestamp()), [FFS 공식 코드](https://github.com/NVlabs/Fast-FoundationStereo).

## RGB·깊이·3D·IMU 통합 뷰어

```bash
cd <저장소 루트>   # 예: /home/leajeajun/Desktop/StereoDepthSeg
./venv_ffs/bin/python z_phone_stereo.py \
  --physical 2 5 --calib-stereo calib_phone_pair.json --yolo seg \
  --rgbd-viewer --out phone_stereo/runs/my_view
```

`--yolo seg`는 객체 인식을 수행하고 RGB 패널에 표시한다. 객체별 3D 모델 생성·맵 누적 기능은 제거했다. 현재 **전체 장면**의 RGB/깊이/컬러 점군/IMU를 표시한다. [RealSense D435i의 RGB-D·IMU 보기](https://github.com/realsenseai/librealsense/blob/master/doc/d435i.md)를 참고한 폰 전용 뷰어이며, 입력은 기존 폰 스테레오와 FFS 추정 깊이다. RealSense SDK 장치 에뮬레이션은 하지 않는다.

한 화면의 RGB·깊이·점군은 같은 완료된 추론 결과를 사용하고 IMU도 해당 왼쪽 렌즈 노출 시각에 대응한다. 카메라 수신 FPS와 별개로 추론이 끝날 때 갱신된다. 컬러 영상과 깊이는 정류된 왼쪽 영상 좌표로 정렬되어 있다.

- 상단 RGB/깊이 클릭: 해당 픽셀의 rectified Z, 렌즈에서의 거리, 원래 왼쪽 렌즈 좌표계 XYZ(m). 무효 깊이는 `invalid depth`.
- 왼쪽 아래 3D 패널: 드래그 회전, 휠 확대, Shift+드래그 이동, R 초기화.
- C: 점군 RGB/깊이 색 전환. F: 표시 프레임 고정/해제(카메라와 추론은 계속).
- IMU 패널: 자이로 rad/s, 중력 제거 선가속도 m/s², 중력 m/s², 센서-노출 시간차, 게임 회전벡터의 기기 방향 축.
- E: 현재 표시 프레임을 `rgbd_captures/<timestamp>/`에 저장. Q: 종료.

`rgbd/`에는 약 5초 간격과 종료 시 마지막 표시 프레임을 저장한다. `rgb.png`, `depth_color.png`, `viewer.png`, `depth_mm.png`(uint16, 1=1mm, 0=무효), `rgbd.npz`(float32 깊이 m·valid·원래 렌즈 좌표 점·K·R1), `scene.ply`, 회전 가능한 `scene.html`, `frame.json`(시각/단위/좌표계/IMU). PNG의 깊이는 정류 좌표 Z이고 PLY의 점은 원래 왼쪽 렌즈 좌표라 회전 R1이 메타데이터에 포함된다. IMU 벡터는 Android 기기 축이며 선가속도는 중력을 포함한 원시 가속도와 구분한다.

`--depth-range 0.3 3`은 깊이 색 범위 및 표시/PLY 점군의 Z 범위를 정한다. NPZ와 uint16 깊이 PNG에는 이 표시 범위로 잘라내지 않은 유효 깊이가 들어간다. `--headless`에서도 파일 생성 가능. `--offline <bundle>`과 함께 쓰면 `--out` 아래 `rgbd/<bundle 이름>/`으로 저장한다.
