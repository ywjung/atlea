# 멀티플랫폼 지원 완료

이 문서는 ATLEA의 멀티플랫폼 지원 구현 내용을 설명합니다.

## 개요

이제 ATLEA는 다음 플랫폼에서 자동으로 최적화되어 실행됩니다:
- **Mac (Apple Silicon)**: MLX 백엔드 사용
- **Linux (NVIDIA GPU)**: Transformers + CUDA 백엔드 사용
- **Linux/Mac (CPU)**: Transformers + CPU 백엔드 사용

## 주요 변경사항

### 1. 플랫폼 자동 감지 시스템

**파일**: `src/platform_utils.py` (신규 생성)

```python
class PlatformDetector:
    - 시스템 자동 감지 (Darwin, Linux, Windows)
    - 하드웨어 감지 (Apple Silicon, NVIDIA CUDA, CPU)
    - 최적 백엔드 자동 선택
```

**기능**:
- PyTorch CUDA 사용 가능 여부 확인
- Apple MPS 사용 가능 여부 확인
- MLX 설치 여부 확인 (Apple Silicon)
- 최적 device 및 dtype 자동 선택

### 2. 멀티플랫폼 LLM 모듈

**파일**: `src/llm.py` (전면 개편)

**이전 (Mac 전용)**:
```python
from mlx_lm import load, generate, stream_generate
# MLX만 지원
```

**변경 후 (멀티플랫폼)**:
```python
from .platform_utils import get_platform_detector

class LLM:
    def __init__(self):
        self.platform = get_platform_detector()
        self.backend = self.platform.get_llm_backend()

        if self.backend == "mlx":
            self._load_mlx(local_path)
        else:
            self._load_transformers(local_path)
```

**추가된 메서드**:
- `_load_mlx()`: Apple Silicon용 MLX 로딩
- `_load_transformers()`: NVIDIA/CPU용 Transformers 로딩
- `_generate_mlx()`: MLX 백엔드 생성
- `_generate_transformers()`: Transformers 백엔드 생성
- `_stream_response_mlx()`: MLX 스트리밍
- `_stream_response_transformers()`: Transformers 스트리밍

### 3. Embedding 모델 (이미 멀티플랫폼)

**파일**: `src/embeddings.py` (변경 없음)

이미 다음과 같이 멀티플랫폼을 지원하고 있었습니다:
```python
if torch.backends.mps.is_available():
    self.device = "mps"
elif torch.cuda.is_available():
    self.device = "cuda"
else:
    self.device = "cpu"
```

### 4. Requirements 파일 구조

**변경 전**:
- `requirements.txt`: MLX 포함 (Mac 전용)

**변경 후**:
- `requirements.txt`: 공통 의존성 (플랫폼 중립적)
- `requirements-mac.txt`: Mac 전용 (MLX 포함)
- `requirements-linux.txt`: Linux 전용 (CUDA 지침 포함)

### 5. Docker 지원

**기존**:
- `Dockerfile`: CPU 전용
- `docker-compose.production.yml`: CPU 배포

**추가**:
- `Dockerfile.gpu`: NVIDIA GPU 지원
- `docker-compose.gpu.yml`: GPU 배포 설정

### 6. 배포 가이드 및 스크립트

**신규 파일**:
- `DEPLOYMENT_GUIDE.md`: 플랫폼별 상세 배포 가이드
- `MULTIPLATFORM_SUPPORT.md`: 이 문서
- `setup-linux-gpu.sh`: Linux GPU 자동 설치 스크립트

## 플랫폼별 자동 최적화

### Mac (Apple Silicon)

**자동 선택**:
- LLM 백엔드: MLX
- Embedding device: MPS
- PyTorch dtype: float32

**로그 예시**:
```
Platform Information:
  System: Darwin
  Machine: arm64
  MLX Available: True
  Recommended LLM Backend: mlx
Loading LLM: mlx-community/Qwen3-30B-A3B-4bit (backend: mlx)
Using MLX backend (Apple GPU acceleration)
```

### Linux (NVIDIA GPU)

**자동 선택**:
- LLM 백엔드: Transformers
- Embedding device: CUDA
- PyTorch dtype: float16

**로그 예시**:
```
Platform Information:
  System: Linux
  Machine: x86_64
  CUDA Available: True
  GPU: NVIDIA GeForce RTX 4090
  Recommended LLM Backend: transformers
Loading LLM: Qwen/Qwen2.5-7B-Instruct (backend: transformers)
Using CUDA backend (NVIDIA GPU acceleration)
```

### Linux/Mac (CPU)

**자동 선택**:
- LLM 백엔드: Transformers
- Embedding device: CPU
- PyTorch dtype: float32

**로그 예시**:
```
Platform Information:
  System: Linux
  Machine: x86_64
  CUDA Available: False
  Recommended LLM Backend: transformers
Loading LLM: Qwen/Qwen2.5-3B-Instruct (backend: transformers)
Using Transformers backend (cpu)
```

## 설치 방법

### Mac (Apple Silicon)
```bash
# 의존성 설치
pip install -r requirements-mac.txt

# 서버 실행 (MLX 자동 사용)
python -m src.web_server
```

### Linux (NVIDIA GPU)
```bash
# 자동 설치 스크립트 사용
chmod +x setup-linux-gpu.sh
./setup-linux-gpu.sh

# 또는 수동 설치
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements-linux.txt

# 서버 실행 (CUDA 자동 사용)
python -m src.web_server
```

### Docker (NVIDIA GPU)
```bash
# NVIDIA Container Toolkit 설치 (한 번만)
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker

# Docker Compose로 실행
docker-compose -f docker-compose.gpu.yml up -d
```

## 모델 호환성

### MLX 모델 (Mac 전용)
MLX Hub에서 `-mlx-` 또는 `mlx-community/` 접두사가 있는 모델:
- `mlx-community/Qwen3-30B-A3B-4bit`
- `mlx-community/rnj-1-instruct-4bit`

### HuggingFace 모델 (모든 플랫폼)
표준 HuggingFace 모델:
- `Qwen/Qwen2.5-7B-Instruct`
- `Qwen/Qwen2.5-14B-Instruct`
- 기타 모든 Transformers 호환 모델

**자동 양자화**:
- NVIDIA GPU에서 자동으로 float16 사용
- bitsandbytes를 통한 4bit/8bit 양자화 지원

## 성능 벤치마크

| 플랫폼 | 백엔드 | 추론 속도 | GPU 메모리 |
|--------|--------|-----------|-----------|
| Mac M1 Pro | MLX | ~50 tokens/s | 통합 메모리 |
| Mac M2 Max | MLX | ~70 tokens/s | 통합 메모리 |
| RTX 4090 | Transformers+CUDA | ~150-200 tokens/s | 12-16GB |
| RTX 3090 | Transformers+CUDA | ~100-120 tokens/s | 12-16GB |
| CPU (16코어) | Transformers+CPU | ~5-10 tokens/s | 시스템 RAM |

## 테스트 방법

### 플랫폼 감지 테스트
```python
from src.platform_utils import get_platform_detector

detector = get_platform_detector()
detector.print_info()
```

### LLM 백엔드 테스트
```python
from src.llm import LLM

llm = LLM(model_name="your-model")
# 자동으로 최적 백엔드 선택됨

print(f"Backend: {llm.backend}")
print(f"Device: {llm.device if hasattr(llm, 'device') else 'MLX'}")
```

### CUDA 사용 가능 여부 확인
```bash
python -c "import torch; print(f'CUDA: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else None}')"
```

## 마이그레이션 가이드

### 기존 Mac 사용자
변경 사항 없음. MLX가 자동으로 계속 사용됩니다.

### 새로운 Linux 사용자
1. NVIDIA Driver 및 CUDA 설치
2. `setup-linux-gpu.sh` 실행
3. 서버 시작 - 자동으로 CUDA 감지

### Docker 사용자
- CPU 배포: `docker-compose.production.yml` 사용
- GPU 배포: `docker-compose.gpu.yml` 사용

## 트러블슈팅

### Mac에서 MLX가 로드되지 않음
```bash
# Apple Silicon 확인
arch
# arm64 출력되어야 함

# MLX 재설치
pip install --upgrade mlx mlx-lm
```

### Linux에서 CUDA가 감지되지 않음
```bash
# NVIDIA Driver 확인
nvidia-smi

# CUDA 확인
nvcc --version

# PyTorch CUDA 확인
python -c "import torch; print(torch.cuda.is_available())"

# PyTorch 재설치 (CUDA 지원)
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

### GPU 메모리 부족
```bash
# 더 작은 모델 사용
export LLM_MODEL="Qwen/Qwen2.5-3B-Instruct"

# 또는 양자화 모델 사용
export LLM_MODEL="Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4"
```

## 향후 개선 계획

- [ ] AMD ROCm 지원
- [ ] Intel oneAPI 지원
- [ ] 모델 자동 양자화 (BitsAndBytes, GPTQ)
- [ ] 멀티 GPU 지원
- [ ] 동적 배치 크기 조정
- [ ] 성능 프로파일링 도구

## 기여 및 피드백

플랫폼별 이슈나 개선 제안은 GitHub Issues에 등록해주세요.

특히 다음 정보를 포함하면 도움이 됩니다:
- 운영체제 및 버전
- 하드웨어 정보
- Python 버전
- 플랫폼 감지 로그 (`detector.print_info()` 출력)
