./venv_ffs/bin/python z_phone_stereo.py --physical 2 5 --calib-stereo calib_phone_pair.json --yolo seg --rgbd-viewer --out phone_stereo/runs/my_view 

실행


빠르게 하는 법

sudo systemctl restart nvidia-powerd
nvidia-smi --query-gpu=clocks.sm,clocks.max.sm --format=csv


부하확인
cd ~/Desktop/StereoDepthSeg && uptime -s && ./venv_ffs/bin/python -c "
import time,cv2,torch,lib_ffs
L=cv2.imread('phone_stereo/runs/scene/captures/197065004375667/camera_2.png');R=cv2.imread('phone_stereo/runs/scene/captures/197065004375667/camera_5.png')
m=lib_ffs.load(valid_iters=4)
for i in range(5):
    t=time.perf_counter();lib_ffs.infer(m,L,R,valid_iters=4);torch.cuda.synchronize();print('ffs %.0f ms'%((time.perf_counter()-t)*1000))
" 2>&1 | grep -E "^20|ffs"
