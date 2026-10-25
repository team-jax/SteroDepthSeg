# 저장소 전체 분석 (2026-10-22 작성, 2026-10-25 갱신)

이 문서는 저장소의 코드·문서·데이터 파일 60개를 모두 읽고 정리한 결과다. 같은 날 현재 PC와 연결된 폰에서 직접 확인한 실행 환경도 함께 적었다.
캘리브레이션 실행 절차는 [doc_CALIBRATION.md](doc_CALIBRATION.md)에 있다.

---

## 1. 이 저장소가 하는 일

카메라 영상에서 객체를 인식(YOLO)하고, 스테레오(두 시점) 삼각측량으로 객체의 **거리·3D 좌표·크기(미터)**를 구한다.
개발은 다음 세 단계를 거쳤고, 이전 단계의 코드도 지우지 않고 남아 있다.

| 세대 | 카메라 | 깊이 방식 | 진입 스크립트 | 캘리 파일 |
|---|---|---|---|---|
| 1 | 노트북 웹캠 1대를 옮겨 2장 촬영 (`--board`/`--mono`) | SIFT 희소 삼각측량 | `z_capture.py` → `z_reconstruct.py` | `calib.json` |
| 2 | 웹캠 + 폰(scrcpy/v4l2loopback) 2대 | SIFT 희소 / FFS 조밀 | `z_stereo_pose.py`, `z_object_depth.py` | `calib.json`, `calib_phone.json`, `calib_stereo.json` |
| **3 (현재 주력)** | **폰 후면 두 물리 렌즈(초광각 2 + 광각 5) 동시 스트림** | **Fast-FoundationStereo(FFS) 조밀 시차** + YOLO seg/bbox | `z_phone_stereo.py` | **`calib_phone_pair.json`** |

README.md 의 "실행" 절이 3세대다. 1·2세대는 `doc_HOW_TO_RUN.md` 앞부분에 설명돼 있다.

---

## 2. 파일 지도

### 2.1 라이브러리 (`lib_*.py`)

| 파일 | 역할 | 핵심 함수 |
|---|---|---|
| `lib_calib.py` | 화면 체커보드 PNG 생성(기준막대 포함), 코너 검출, 단일 카메라 `calibrateCamera` | `make_target`, `square_m_from_ruler`, `find_corners(fast=)`, `calibrate`, `save_calib/load_calib` |
| `lib_cam.py` | 웹캠 열기(1280×720 MJPG 강제), 두 카메라 `read_pair`, 라이브 루프 | `open_camera`, `read_pair`, `live_capture` |
| `lib_stereo.py` | 희소 삼각측량 코어(1대/2대 공용), 보드 PnP 포즈, Sampson 에피폴라, 박스 피팅 | `pose_from_board`, `reconstruct`, `epipolar_sampson`, `planar_box`, `check_board_consistency` |
| `lib_rectify.py` | `stereoRectify` + remap, 시차→깊이, 정류 검사(`epipolar_check`) | `rectify_maps`, `rectify_pair`, `disparity_to_depth`, `epipolar_check` |
| `lib_ffs.py` | FFS 추론 어댑터(venv_ffs 전용, triton 자동 감지) | `load`, `infer` |
| `lib_detect.py` | YOLO11 검출/세그(retina mask), 수동 ROI | `detect_yolo`, `draw` |
| `lib_plane.py` | 보드 평면과 광선의 교점으로 1장 측정 (`z_live.py`) | `board_plane`, `object_from_box` |
| `lib_viz.py` | Open3D 3D 맵 | `build`, `show` |
| `lib_phone_stereo.py` | 폰 USB 패킷 수신(NV21 + SENS 센서 패킷), timestamp 짝짓기 | `PhoneReceiver`, `FramePairer` |
| `lib_phone_calib.py` | **폰 두 렌즈 캘리**: 공장값 변환, 장면 회전 보정, 보드 stereoCalibrate, 실측 거리 yaw 고정 | `factory_stereo`, `refine_pose`, `board_stereo_calibrate`, `pin_yaw_known_distance`, `evaluate_pairs` |
| `lib_phone_depth.py` | 폰 캘리 검증 + FFS/YOLO 객체 깊이 + 중력 정렬 + 자이로 동기 보상 | `load_phone_calibration`, `PhoneDepth`, `skew_rotation`, `gravity_frame` |
| `lib_phone_motion.py` | 폰을 옮긴 두 시점을 넓은 baseline 스테레오로 사용(회전벡터 + 영상 + 스테레오 스케일) | `analyze` |
| `lib_rgbd_viewer.py`, `lib_pointcloud_*.py` | RGB·깊이·점군·IMU 통합 뷰어, PLY/HTML 내보내기 | `RGBDViewer` |

### 2.2 실행 스크립트 (`z_*.py`)

| 파일 | 실행 venv | 하는 일 |
|---|---|---|
| `z_calibrate.py` | venv | 타겟 PNG 생성(`--make-target --screen s24/laptop`), 웹캠 단일 캘리(`--capture`/`--run`), 웹캠 2대 캘리(`--capture-stereo`/`--run-stereo`) |
| `z_capture.py` | venv | 1세대 본 촬영 (`--board`/`--mono`/`--stereo`) → `shots/` |
| `z_reconstruct.py` | venv | 희소 복원 + YOLO + Open3D → `results.json` |
| `z_stereo_pose.py` | venv | 보드 없이 Essential 행렬로 두 카메라 포즈 + 스케일(`--rescale`/`--baseline-mm`/`--known-mm`) |
| `z_object_depth.py` | venv_ffs | 조밀(FFS) 객체 깊이 → `out_dense/` |
| `z_phone_stereo.py` | venv(수신·저장) / venv_ffs(FFS) | **폰 앱 설치·렌즈 조회·스트림·저장·라이브 depth·뷰어** |
| `z_phone_calib.py` | venv | **폰 캘리 CLI**: `--factory` / `--refine` / `--known` / `--board` / `--check` |
| `z_phone_motion.py` | venv / venv_ffs | 이동 스테레오 |
| `z_live.py`, `z_view.py` | venv | 1장 평면 측정 라이브, 2대 미리보기 |
| `z_selftest.py` | venv | GPU·카메라 없이 도는 회귀 테스트 31항목 |
| `z_ffs_smoke.py`, `z_make_synth_pair.py` | venv_ffs / venv | FFS 스모크, 정답 합성 쌍 생성 |

### 2.3 폰 쪽 (`phone_stereo/`)

- `android/src/.../MainActivity.java`: Camera2 logical camera 0에 물리 출력 2~3개를 연결한다. NV21 프레임을 ADB 포워딩 TCP 8765로 보낸다. 초점은 `LENS_FOCUS_DISTANCE`로 고정한다(기본 1 m). 프레임 timestamp는 물리 `SENSOR_TIMESTAMP`로 보정하고, 센서 패킷(자이로·중력·회전벡터·기압·frame_timing)도 함께 보낸다. 같은 디렉터리의 `CaptureTimestampMatcher.java`는 이미지와 촬영 결과를 timestamp로 정확히 연결한다.
- `build_android.py`: SDK 35를 체크섬 검증한 뒤 내려받아 APK를 빌드한다(결과물은 `tools/android-sdk`).
- `cameras_s24.json`: 이전 폰 **S24(SM-S921N)** 의 `--list` 결과 사본이다. 현재 폰(S25)의 공장값은 `--list` 가 `phone_stereo/runs/cameras.json` 에 저장하고 캘리 CLI 가 그 파일을 우선 읽는다.
- 테스트 `test_receiver.py`, `test_timestamp_matcher.py`, `test_rgbd_viewer.py`, `test_phone_depth.py`(라이브 정류 판정), `tests/CaptureTimestampMatcherTest.java` — 합계 21개.

### 2.4 문서·데이터

| 파일 | 내용 |
|---|---|
| `README.md` | 3세대 실행 한 줄 요약 |
| `doc_CALIBRATION.md` | 폰 두 렌즈 캘리 1~6단계 + 웹캠 부록 + S25 실제 결과·검증 기록 |
| `doc_REPO_ANALYSIS.md` | 이 문서 |
| `phone_stereo/README.md` | 폰 스테레오 상세: 캘리 4단계 표, 동기화, 센서, 뷰어 |
| `doc_HOW_TO_RUN.md` | 1·2세대 절차 + 폰 캘리 명령 |
| `STATUS.md` | 작업 이력, 문제점 1~18, 파라미터 변경 이력 |
| `HARNESS.md` | 작업 규칙(계획→승인→구현, 근거 필수, 코드·주석·MD 동기화) |
| `doc_DEPTH_CODE_REVIEW.md`, `doc_YOLO_FAST_FOUNDATIONSTEREO_RESEARCH.md`, `research/` | GPT 코드 검토 12항목과 재현 스크립트, FFS 조사 |
| `calib.json` | HP 웹캠 1280×720, RMS 0.23 px, 41뷰 (2026-09-21, 이전 노트북) |
| `calib_phone.json` | 폰 초광각 1280×720 단일 캘리 (2세대 scrcpy 경로) |
| `calib_phone_pair.json` | **S25** 초광각2+광각5 640×480 보드 캘리, `metric`, RMS 0.105 px, baseline 16.64 mm (2026-10-25). 이전 S24 판은 git 기록 |
| `target_s24.png`, `target_laptop.png` | 화면 체커보드 (15×6 내부 코너, 기준막대 2000/1000 px) |

---

## 3. 핵심 데이터 흐름 (3세대)

```
폰 앱(Camera2, 물리 2·5, 640×480 NV21, 초점 1 m 고정)
   │ ADB tcp:8765 (프레임 + SENS 센서 패킷)
   ▼
lib_phone_stereo.PhoneReceiver ── 물리 노출 timestamp로 짝짓기 (--max-skew-ms 35)
   │ pair
   ▼
lib_phone_depth.PhoneDepth
   ├ load_phone_calibration: phone.logical/physical/image_size 일치 검사, 순서가 반대면 swap
   ├ skew_rotation: 두 렌즈 노출 시각 차 동안의 자이로 회전 → R·Rg 로 정류
   ├ lib_rectify.rectify_maps/rectify_pair  (check_rectification: 질감 있고 정지한(motion_px<1) 쌍 3개의 dy 중앙값 ≥1px 이면 예외)
   ├ lib_ffs.infer → 시차 → 깊이 Z = f·b/d
   ├ lib_detect.detect_yolo(정류 왼쪽) → z_object_depth.aggregate (seg 마스크/bbox)
   └ gravity_frame → center_world_m
   ▼
depth.json / overlay / RGB-D 뷰어(rgbd/)
```

캘리 파일의 `scale_status`가 `metric`이 아니면 객체마다 `scale_not_validated:<status>` 경고가 붙는다.

---

## 4. 캘리브레이션 구조

### 4.1 폰 두 렌즈 (현재 주력) — `z_phone_calib.py`

| 단계 | 바뀌는 것 | 고정되는 것 | 결과 `scale_status` |
|---|---|---|---|
| `--factory` | — (Camera2 공장 K·dist·pose를 OpenCV 규약으로 변환) | 전부 공장값 | `factory_unverified` |
| `--refine <장면 번들>` | roll·pitch(+광각 fx 스케일) — Sampson 오차 LM | yaw, \|T\| | `factory_baseline_refined` |
| `--known <번들> --known-m --roi` | yaw (ROI 시차가 f·b/Z가 되게) | baseline | `known_distance_pinned` |
| `--board <보드 번들>` | R, T (기본: K·dist 고정). `--free-intrinsics`: 렌즈별 `calibrateCamera` 로 K·dist 를 먼저 구한 뒤 고정하고 R, T | K, dist | `metric` (rms≤1 px, 뷰≥8, baseline 공장값 ±15%, K 고정인데 refine 광각 스케일 편차 >5% 면 거부) 또는 `board_unreliable`(덮어쓰지 않고 `.unreliable.json`) |
| `--check <번들>` | 검사만: 정류 후 dy 중앙값 <1 px, 인라이어 ≥0.7 | | |

이 구조가 필요한 이유는 다음과 같다(STATUS 16·18).
- baseline 이 약 16 mm 라 1 m 에서 시차가 7 px 뿐이다. yaw 0.1° 오차는 시차 0.76 px 편향, 즉 1 m 에서 깊이 11% 오차가 된다.
- dy(세로 시차)로는 yaw 가 관측되지 않는다. 그래서 refine 은 yaw 를 고정하고, yaw 는 보드나 실측 거리로만 잡는다.
- 두 렌즈 노출은 하드웨어 동기가 아니다(APPROXIMATE). 보드 촬영은 반드시 `--still --board-hud`(정지 순간, 양쪽 렌즈 검출)로 한다.
- 광각 렌즈는 AF라 초점이 움직이면 fx가 바뀐다. 그래서 초점을 고정(`--focus-m`)하고, 캘리 때 쓴 값을 json의 `focus_m`에 기록한다.
- S25 는 초광각 640×480 스트림이 크롭이라 공장 K(fx 256)가 실제(312)와 다르다. 그래서 S25 보드 캘리는 `--free-intrinsics` 가 필수다.

### 4.2 웹캠 단일·2대 — `z_calibrate.py`

화면에 띄운 체커보드(`--make-target`)의 기준막대 간격을 자로 재서 `--ruler-mm` 으로 넣는다. 이 값으로 사각형 실치수를 정한다.
`--run`은 calibrateCamera를 실행하고 게이트(RMS<1 px, 뷰≥15, 커버리지≥12/16)를 검사한다. `--run-stereo`는 각 카메라를 단일 캘리한 뒤 `stereoCalibrate(FIX_INTRINSIC)`를 실행한다.

---

## 5. 이 PC·이 폰에서 직접 확인한 현재 상태 (2026-10-22 조사, 2026-10-25 갱신)

| 항목 | 저장소 기록 | 현재 실제 | 영향 |
|---|---|---|---|
| 저장소 경로 | `/home/karma/camera` (doc_HOW_TO_RUN, phone_stereo/README) | `/home/leajeajun/Desktop/StereoDepthSeg` | 실행 문서 2곳의 경로를 "저장소 루트"로 수정 (doc_DEPTH_CODE_REVIEW 의 링크는 당시 기록이라 유지) |
| 폰 | Galaxy **S24 SM-S921N** | Galaxy **S25 SM-S931N** (serial R3CXC0BK8XV) | S24 캘리 무효 → **2026-10-25 S25 로 재캘리 완료(`metric`)** |
| 폰 공장 baseline (2↔5) | 15.76 mm | **16.30 mm** | |
| 초광각 2 fx (active array) | 1637.4 | 1599.4 (640×480 환산 256) | 실제 스트림은 크롭: 보드 캘리 fx **312** |
| 광각 5 fx | 2780.1 | 2716.1 (640×480 환산 426) | 보드 캘리 fx 424 (공장값과 일치) |
| 망원 6 pose_translation | (0, −16.6 mm, 0) | (0, 0, 0) — 공장 포즈 없음 | 망원 쌍은 공장값 사용 불가 |
| 광각 focus_calibration | 2 (CALIBRATED) | 1 (APPROXIMATE) | 초점 거리 값의 신뢰도가 낮음 |
| `calib_phone_pair.json` 의 S25 정류 | S24 판: dy 27 px FAIL | **S25 판: dy 0.25~0.55 px**, 라이브 판정 0.31 px | FFS vs 보드 PnP 거리 +0.8% |
| 웹캠 | HP Wide Vision HD (`calib.json`) | 이 노트북(MSI) 내장캠 `/dev/video0` | `calib.json` 무효, 1·2세대를 쓰려면 다시 캘리 필요 |
| GPU | RTX 4060 8 GB | RTX 4050 Laptop 6 GB | 라이브 FFS+YOLO 중앙값 239 ms. 절전 복귀 후 GPU 가 210 MHz·15 W 로 묶여 20배 느려졌던 일 → `nvidia-powerd` 서비스 + `/etc/dbus-1/system.d/nvidia-dbus.conf`(NVIDIA 보안 강화판) 설치, 재부팅으로 해소 |
| `venv` | python 3.10 + requirements.txt | python **3.12**, `pip install -r requirements.txt` 완료 (torch 2.14.0+cu130 CUDA OK, ultralytics 8.4.157, open3d 0.20.0) | 처음엔 opencv·numpy 만 있어 캘리 CLI·selftest import 실패 |
| `venv_ffs` | py3.12, torch 2.6.0+cu124 | 동일, CUDA OK, opencv **5.0.0**, open3d 있음 | FFS·YOLO는 venv_ffs로 |
| `python3.12-dev` | 설치됨(triton 경로, VRAM 1.1 GB) | **없음** → FFS 순수 PyTorch 경로(VRAM 4.4 GB+) | GPU 5.6 GB 라 1280×720 FFS 가 OOM. `--scale 0.5` 로 우회하거나 `sudo apt install python3.12-dev` (sudo 암호 필요) |
| FFS 가중치 | `tools/Fast-FoundationStereo/weights/c/…pth` | 있음 | |
| adb | `tools/platform-tools/adb` | 있음, 폰 인식됨 | |
| 폰 화면 유지 | S24: `stay_on_while_plugged_in 2` | S25: 0 → **2** 로 설정 (2026-10-25) | 화면이 꺼지면 앱이 카메라를 못 연다 |

결론: **S25 두 렌즈 캘리 완료(`metric`), 라이브 depth 정상 동작.** 남은 환경 과제는 `python3.12-dev`(FFS 원해상도) 하나다. 절차·결과는 doc_CALIBRATION.md.

---

## 6. 찾아서 고친 문제 (2026-10-22 ~ 10-25)

| # | 문제 | 상태 |
|---|---|---|
| 1 | `z_phone_stereo.py --list` 는 `runs/<시각>/cameras.json` 에 저장한다. 그런데 `lib_phone_calib.DEFAULT_INVENTORY` 는 `runs/cameras.json` 만 찾고, 없으면 **S24 사본으로 조용히 대체**한다. 새 폰에서 `--factory` 를 실행하면 남의 폰 공장값이 들어간다. | 수정: `--list` 가 `phone_stereo/runs/cameras.json` 에도 저장 |
| 2 | `--base calib_phone_pair.json`(문서의 보드 명령)은 물리 id(["2","5"])만 비교한다. 다른 폰이 만든 파일도 통과해 그 폰의 K/R/T 가 초기값·고정값으로 들어간다. | 수정: 공장 baseline 이 1% 넘게 다르면 거부 |
| 3 | `venv` 에 open3d 가 없어 캘리 CLI 자체가 실행되지 않음 (`lib_stereo` import). | 환경 수정(설치) |
| 4 | `--save-interval` 저장 게이트의 터미널 출력이 `WAIT 0.7s` → `0.6s` … 처럼 숫자가 바뀔 때마다 줄을 찍는다(스팸 방지 의도와 다름). | 수정 |
| 5 | `z_calibrate.py` docstring 의 예시 `--ruler-mm 97.5` 는 세로 타겟 시절 값이다. | 수정: 122.0 |
| 6 | `requirements.txt` 는 python 3.10 기준인데 venv 는 3.12 이고 torch·ultralytics 가 없었다. | 환경 수정(설치), 주석 갱신 |
| 7 | refine/known 경고 문구가 baseline "15.76mm" 로 하드코딩 — S25(16.30 mm)에서 틀린 값 출력 | 수정: 실제 공장 baseline 출력 |
| 8 | 라이브 `PhoneDepth` 가 정류 검사를 첫 쌍에만 함 — 첫 쌍이 질감 없으면(unavailable) 이후 검사를 안 해 **다른 폰 캘리로도 depth 를 계속 냄** (S25+S24 캘리로 실측 재현) | 수정: 판정(ok)이 날 때까지 쌍마다 재검사, 회귀 테스트 `phone_stereo/test_phone_depth.py` |
| 9 | `research/.../reproduce_after.py` 의 `unavailable` 스텁이 손으로 베낀 dict 라 `inlier_frac` 키가 빠져 `dense_nan_export` 가 KeyError | 수정: 실제 `epipolar_check` 반환값을 스텁으로 사용 (기록 결과와 다시 일치) |
| 10 | K 고정 보드 캘리가 틀린 K 로도 RMS<1 px 로 `metric` 통과(합성: 거리 −15%) | 수정: refine 광각 스케일 편차 >5% 인데 `--free-intrinsics` 없으면 `board_unreliable` |
| 11 | `--free-intrinsics` 의 K·R·T 공동 추정이 실데이터에서 틀린 해(baseline 19.75 mm) | 수정: 렌즈별 `calibrateCamera` 후 R·T 만 → 16.64 mm |
| 12 | 화면 꺼진 폰에서 촬영 시작 시 `cannot open camera from background` | 수정: 시작 전 화면 깨우기·잠금화면 넘기기, 원인 안내 메시지 |
| 13 | 보드를 PC 화면에 띄우면 촬영 상태를 볼 수 없어 3회 0장 | 추가: `--show-board` (1:1 확인, 상태 테두리, 두 렌즈 뷰파인더) |
| 14 | 라이브 정류 판정을 흔들린 한 쌍으로 해서 멈춤 | 수정: 정지한(`motion_px`<1) 질감 쌍 3개 중앙값 |
| 15 | 두 렌즈 노출 차 자이로 보상이 항상 0° (표본 구간 밖 적분 누락) | 수정: 표본 구간 겹침 적분 |

수정 내역과 테스트 결과는 doc_CALIBRATION.md의 "검증 기록"과 STATUS.md 에 있다.
