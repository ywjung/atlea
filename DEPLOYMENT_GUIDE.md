# Multi-Platform Deployment Guide

이 문서는 Mac (Apple Silicon), Linux (NVIDIA GPU), Linux (CPU) 환경에서 RAG 챗봇을 배포하는 방법을 설명합니다.

## 목차
1. [Mac (Apple Silicon) 배포](#mac-apple-silicon-배포)
2. [Linux (NVIDIA GPU) 배포](#linux-nvidia-gpu-배포)
3. [Linux (CPU) 배포](#linux-cpu-배포)
4. [Docker 배포](#docker-배포)
5. [플랫폼 자동 감지](#플랫폼-자동-감지)

---

## Mac (Apple Silicon) 배포

### 시스템 요구사항
- macOS 12.0 이상
- Apple Silicon (M1/M2/M3 시리즈)
- Python 3.10 이상
- 최소 16GB RAM 권장

### 설치 방법

1. **저장소 클론**
```bash
git clone <repository-url>
cd chatbot_redis
```

2. **가상 환경 생성**
```bash
python3 -m venv venv
source venv/bin/activate
```

3. **의존성 설치**
```bash
pip install --upgrade pip
pip install -r requirements-mac.txt
```

4. **Redis 설치 및 실행**
```bash
brew install redis
brew services start redis
```

5. **환경 변수 설정**
```bash
cp .env.example .env
# .env 파일 편집
```

6. **서버 실행**
```bash
python -m src.web_server
```

### Mac에서의 특징
- **MLX 백엔드**: Apple GPU 최적화를 위해 MLX 사용
- **MPS 가속**: PyTorch도 Apple Metal Performance Shaders 사용
- **빠른 추론**: Apple Silicon에 최적화된 모델 실행

---

## Linux (NVIDIA GPU) 배포

### 시스템 요구사항
- Ubuntu 20.04 이상 (또는 호환 Linux 배포판)
- NVIDIA GPU (CUDA Compute Capability 7.0+)
- NVIDIA Driver 525.x 이상
- CUDA 12.1 이상
- Python 3.10 이상
- 최소 16GB RAM, GPU 메모리 8GB 이상 권장

### 설치 방법

1. **NVIDIA Driver 설치**
```bash
# Ubuntu 예시
sudo ubuntu-drivers devices
sudo ubuntu-drivers autoinstall
sudo reboot
```

2. **CUDA Toolkit 설치**
```bash
# CUDA 12.1 설치 예시
wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64/cuda-keyring_1.1-1_all.deb
sudo dpkg -i cuda-keyring_1.1-1_all.deb
sudo apt-get update
sudo apt-get -y install cuda-12-1
```

3. **저장소 클론 및 가상 환경**
```bash
git clone <repository-url>
cd chatbot_redis
python3 -m venv venv
source venv/bin/activate
```

4. **의존성 설치**
```bash
pip install --upgrade pip

# 먼저 PyTorch를 CUDA 지원과 함께 설치
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 나머지 의존성 설치
pip install -r requirements-linux.txt
```

5. **Redis 설치 및 실행**
```bash
sudo apt-get update
sudo apt-get install redis-server
sudo systemctl start redis-server
sudo systemctl enable redis-server
```

6. **환경 변수 설정**
```bash
cp .env.example .env
# .env 파일 편집
```

7. **GPU 확인**
```bash
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}'); print(f'GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"None\"}')"
```

8. **서버 실행**
```bash
python -m src.web_server
```

### Linux NVIDIA GPU에서의 특징
- **Transformers + CUDA**: NVIDIA GPU 최적화
- **Float16 연산**: GPU 메모리 절약 및 속도 향상
- **자동 device_map**: 큰 모델도 GPU 메모리에 효율적으로 로드
- **병렬 처리**: CUDA를 활용한 빠른 임베딩 및 추론

---

## Linux (CPU) 배포

CPU만 사용하는 환경에서도 실행 가능하지만, 성능이 제한됩니다.

### 설치 방법

1-5단계는 NVIDIA GPU 배포와 동일

6. **CPU용 PyTorch 설치**
```bash
pip install torch torchvision torchaudio
pip install -r requirements-linux.txt
```

7. **서버 실행**
```bash
python -m src.web_server
```

### 성능 최적화
- 더 작은 모델 사용 권장 (예: 3B 모델)
- 배치 크기 줄이기
- max_tokens 제한

---

## Docker 배포

### Mac (Apple Silicon) Docker

**주의**: Docker Desktop for Mac은 MLX를 지원하지 않으므로 네이티브 설치 권장

### Linux (NVIDIA GPU) Docker

1. **NVIDIA Container Toolkit 설치**
```bash
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | sudo tee /etc/apt/sources.list.d/nvidia-docker.list

sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo systemctl restart docker
```

2. **Docker Compose로 실행**
```bash
docker-compose -f docker-compose.production.yml up -d
```

3. **GPU 확인**
```bash
docker exec chatbot-app nvidia-smi
```

---

## SearXNG + Crawl4AI 배포

SearXNG는 자체 호스팅 메타 검색 엔진으로, Tavily의 대안으로 사용할 수 있습니다.

### 시작 방법

```bash
# SearXNG + Crawl4AI 시작
docker compose -f docker-compose.searxng.yml up -d

# 상태 확인
docker ps | grep -E "searxng|crawl4ai"
```

### 서비스 정보

| 서비스 | 포트 | 설명 |
|--------|------|------|
| SearXNG | 8888 | 메타 검색 엔진 (Google, Bing, DuckDuckGo 등) |
| Crawl4AI | 11235 | 웹 페이지 콘텐츠 추출 |

### 설정 방법

1. **관리자 페이지 접속**: `http://localhost:8000/admin.html`

2. **Hybrid RAG 설정**에서:
   - 웹 검색 프로바이더: `SearXNG (자체 호스팅)` 선택
   - SearXNG URL: `http://localhost:8888` 입력

3. **설정 저장**

### SearXNG 엔진 설정

`searxng/settings.yml`에서 검색 엔진 활성화/비활성화:

```yaml
engines:
  - name: google
    disabled: false
  - name: bing
    disabled: false
  - name: duckduckgo
    disabled: false
  - name: stackoverflow
    engine: stackexchange
    site: stackoverflow
    categories: [general, it]
    disabled: false
```

### 헬스 체크

```bash
# SearXNG 상태
curl http://localhost:8888/healthz

# Crawl4AI 상태
curl http://localhost:11235/health
```

### 문제 해결

**SearXNG 검색 에러**:
```bash
# 로그 확인
docker logs searxng --tail 50

# 특정 엔진 에러 시 settings.yml에서 비활성화
# 예: startpage 에러 → disabled: true 설정
```

**Crawl4AI 메모리 부족**:
```yaml
# docker-compose.searxng.yml
deploy:
  resources:
    limits:
      memory: 4G  # 필요시 증가
```

---

## 플랫폼 자동 감지

프로그램은 시작 시 자동으로 플랫폼을 감지하고 최적의 백엔드를 선택합니다:

```python
# src/platform_utils.py
PlatformDetector 클래스가 자동으로:
1. 현재 시스템 감지 (Darwin, Linux, Windows)
2. 하드웨어 확인 (Apple Silicon, NVIDIA GPU, CPU)
3. 최적 백엔드 선택 (MLX, Transformers+CUDA, Transformers+CPU)
```

### 로그 예시

**Mac (Apple Silicon)**:
```
Platform Information:
  System: Darwin
  Machine: arm64
  CUDA Available: False
  MPS Available: True
  MLX Available: True
  Recommended LLM Backend: mlx
  Recommended Device: mps
```

**Linux (NVIDIA GPU)**:
```
Platform Information:
  System: Linux
  Machine: x86_64
  CUDA Available: True
  MPS Available: False
  MLX Available: False
  Recommended LLM Backend: transformers
  Recommended Device: cuda
```

---

## 모델 호환성

### MLX 모델 (Mac 전용)
- `mlx-community/Qwen3-30B-A3B-4bit`
- `mlx-community/rnj-1-instruct-4bit`
- MLX Hub의 모든 양자화 모델

### Transformers 모델 (모든 플랫폼)
- HuggingFace Hub의 모든 모델
- 자동 양자화 지원 (4bit/8bit)
- GGUF 형식은 별도 변환 필요

### Embedding 모델 (모든 플랫폼)
- `nlpai-lab/KURE-v1` (한국어)
- `jinaai/jina-embeddings-v3`
- `intfloat/multilingual-e5-large`
- SentenceTransformers 호환 모든 모델

---

## 트러블슈팅

### Mac 관련

**문제**: MLX가 설치되지 않음
```bash
# Rosetta 모드로 실행 중인지 확인
arch
# arm64가 아니면 네이티브 터미널 사용

pip install mlx mlx-lm
```

### Linux NVIDIA 관련

**문제**: CUDA가 감지되지 않음
```bash
# CUDA 설치 확인
nvcc --version
nvidia-smi

# PyTorch CUDA 지원 확인
python -c "import torch; print(torch.cuda.is_available())"

# 재설치
pip uninstall torch torchvision torchaudio
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
```

**문제**: GPU 메모리 부족
```bash
# 현재 사용 중: Qwen3 30B (~20GB RAM 필요)
# 메모리 부족 시 경량 모델로 변경 (별도 다운로드 필요)

# 경량 옵션 (~2GB RAM)
LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit

# 초경량 옵션 (~1.5GB RAM)
LLM_MODEL=mlx-community/Qwen2.5-1.5B-Instruct-4bit
```

### 공통 문제

**문제**: Redis 연결 실패
```bash
# Redis 상태 확인
redis-cli ping
# PONG 응답이 와야 함

# Redis 재시작
# Mac:
brew services restart redis
# Linux:
sudo systemctl restart redis-server
```

---

## 성능 비교

| 플랫폼 | LLM 백엔드 | 상대 속도 | GPU 메모리 |
|--------|-----------|----------|-----------|
| Mac M1 Pro | MLX | 1.0x (기준) | 통합 메모리 |
| Mac M2 Max | MLX | 1.5x | 통합 메모리 |
| RTX 4090 | Transformers+CUDA | 3-4x | 24GB |
| RTX 3090 | Transformers+CUDA | 2-3x | 24GB |
| CPU (16코어) | Transformers+CPU | 0.1-0.2x | 시스템 RAM |

---

## 추가 리소스

- [MLX Documentation](https://ml-explore.github.io/mlx/)
- [PyTorch CUDA Installation](https://pytorch.org/get-started/locally/)
- [Transformers Documentation](https://huggingface.co/docs/transformers/)
- [Redis Documentation](https://redis.io/docs/)

---

## 문의 및 지원

문제가 발생하면 GitHub Issues에 다음 정보와 함께 제보해주세요:
1. 운영체제 및 버전
2. 하드웨어 정보 (GPU 모델 등)
3. Python 버전
4. 에러 로그
5. `python -m src.web_server` 실행 시 나타나는 플랫폼 정보
