#!/usr/bin/env bash
# Pod setup for Look to Listen (Engine B-GPU). Idempotent. About 1 minute on a RunPod PyTorch pod.
# On the pod: bash /workspace/clearvoice_home/pod_setup.sh > /workspace/pod_setup.log 2>&1
set -x
date
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
python -c "import torch,sys;print('python',sys.version.split()[0],'torch',torch.__version__,'cuda',torch.version.cuda,torch.cuda.is_available())"
mkdir -p /workspace/clearvoice_home/checkpoints/AV_MossFormer2_TSE_16K
cd /workspace/clearvoice_home
TV=$(python -c "import torch;print(torch.__version__.split('+')[0])")
CU=$(python -c "import torch;print((torch.version.cuda or '').replace('.',''))")
python -c "import torchvision,torchaudio" 2>/dev/null || pip install -q "torch==$TV" "torchaudio==$TV" torchvision --index-url "https://download.pytorch.org/whl/cu$CU"
pip install -q "numpy<2" einops gdown "huggingface-hub>=0.26.2" joblib "librosa==0.10.2.post1" "opencv-python-headless==4.10.0.84" packaging pydub "python_speech_features==0.6" "rotary_embedding_torch==0.8.3" "scenedetect==0.6.6" scikit_learn "scipy>=1.10.1" "soundfile==0.12.1" torchinfo tqdm yamlargparse fastapi "uvicorn[standard]" websockets
pip install -q --no-deps clearvoice
python -c "from huggingface_hub import hf_hub_download as d; [d('alibabasglab/AV_MossFormer2_TSE_16K', f, local_dir='checkpoints/AV_MossFormer2_TSE_16K') for f in ['last_best_checkpoint','last_best_checkpoint.pt']]"
ls -la checkpoints/AV_MossFormer2_TSE_16K
python gate_g1_pod.py
echo SETUP_DONE
date
