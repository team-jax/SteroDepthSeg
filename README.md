# Camera

폰 스테레오 영상으로 객체를 인식하고 객체별 깊이·거리·크기를 추출합니다. RGB·깊이맵·전체 장면 3D 점군·IMU를 통합 뷰어에서 확인할 수 있습니다.

## 실행

> **현재 폰: Galaxy S25 (SM-S931N), 캘리브레이션 완료(`metric`, 2026-10-25).** `calib_phone_pair.json` 은 이 폰 전용입니다 —
> baseline 16.64 mm, 0.4~0.6 m 에서 거리 오차 약 1%. 폰을 바꾸면 [캘리브레이션 절차](doc_CALIBRATION.md)를 다시 해야 합니다
> (다른 폰의 파일로 실행하면 `Phone rectification failed` 로 멈춥니다).

저장소 루트에서, 폰을 USB로 연결한 뒤 실행합니다. 기존에 구성된 `venv_ffs` 환경과 폰 카메라 앱을 사용합니다.

```bash
./venv_ffs/bin/python z_phone_stereo.py \
  --physical 2 5 --calib-stereo calib_phone_pair.json \
  --yolo seg --rgbd-viewer --out phone_stereo/runs/my_view
```

- `--yolo seg`: 객체 인식·세그멘테이션 및 객체별 깊이·크기·**카메라 기준 회전(yaw/pitch/roll, 라벨 아래 노란 글자)** 추출. 의미·정확도는 [phone_stereo/README.md](phone_stereo/README.md#객체-회전-yaw--pitch--roll).
- `--rgbd-viewer`: RGB·깊이·3D 점군·IMU 표시.
- `--out`: 실행 결과 저장 폴더.

시작 후 처음 몇 초는 폰을 **0.6 m 이상 떨어진 질감 있는 물체**에 대고 가만히 듭니다. 이때 정류(캘리) 검사가 정지한 쌍 3개로 끝나고, 그 뒤엔 자유롭게 움직여도 됩니다.
폰 화면은 프로그램이 켜지만 PIN·패턴 잠금은 직접 풀어야 합니다.

인식한 객체의 3D 모델을 맵에 추가·누적하는 기능은 포함하지 않습니다. `--object-map` 옵션은 제거되었습니다.

뷰어에서 드래그로 3D 회전, 휠로 확대, RGB/깊이 영상 클릭으로 거리·XYZ를 확인합니다. **F**는 화면 고정, **E**는 현재 프레임 내보내기, **Q**는 종료입니다.

설치·보정·저장 파일 등 자세한 설명은 [폰 스테레오 README](phone_stereo/README.md), 캘리브레이션은 [doc_CALIBRATION.md](doc_CALIBRATION.md),
저장소 구조는 [doc_REPO_ANALYSIS.md](doc_REPO_ANALYSIS.md), 작업 이력은 [STATUS.md](STATUS.md)를 참고하세요.

테스트: `./venv/bin/python z_selftest.py` (31항목), `./venv/bin/python -m unittest discover -s phone_stereo -p 'test_*.py'` (21개, Java 테스트에 JDK 필요).
