# 비동기 작업 큐 검토 및 권장사항

## 📋 개요

현재 시스템의 비동기 작업 처리 현황을 분석하고, Celery/RQ와 같은 전문 작업 큐 도입의 필요성 및 구현 방안을 제시합니다.

**작성일**: 2026-01-11
**우선순위**: Priority 3 (Month 1)
**영향도**: Medium-High

---

## 🔍 현재 상태 분석

### 1. 기존 비동기 작업 처리 방식

현재 시스템은 다음 세 가지 방식으로 비동기 작업을 처리하고 있습니다:

#### A. asyncio.create_task() 사용
**위치**: `src/web_server.py`

```python
# 백그라운드 스케줄러 (line 2846)
backup_scheduler_task = asyncio.create_task(backup_scheduler())

# 감사 로그 정리 스케줄러 (line 2851)
audit_cleanup_scheduler_task = asyncio.create_task(audit_cleanup_scheduler())

# 질문 풀 생성 (line 2840)
asyncio.create_task(generate_questions_pool_background())

# 인덱스 정리 (line 4237)
asyncio.create_task(cleanup_old_index_async(old_index_name))
```

**특징**:
- 애플리케이션 프로세스 내에서 실행
- 메모리 공유, 빠른 작업 시작
- 프로세스 재시작 시 작업 손실 위험
- 작업 큐잉, 재시도, 모니터링 기능 없음

#### B. FastAPI BackgroundTasks 사용
**위치**: `src/web_server.py`

```python
# 리인덱싱 작업 (line 4656)
@app.post("/api/reindex", tags=["Documents"])
async def reindex(
    request: Request,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_active_user)
):
    background_tasks.add_task(run_reindex_task)
```

**특징**:
- FastAPI 요청 컨텍스트에서 작업 실행
- 요청 완료 후에도 작업 계속
- 작업 진행 상황 추적 가능 (Redis 사용)
- 단일 서버 환경에 한정

#### C. 동기 처리 (블로킹)
**위치**: `src/web_server.py:5343`

```python
# 문서 업로드 시 처리 (동기)
chunks = doc_processor.process_document(str(file_path))  # BLOCKING
embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)  # BLOCKING
```

**문제점**:
- 대용량 문서 처리 시 API 응답 지연
- 사용자가 업로드 완료까지 대기 필요
- 타임아웃 위험 (큰 파일, 많은 청크)
- 병렬 업로드 제한

### 2. 통계 데이터

현재 시스템에서 확인된 비동기 작업 수:

```bash
$ grep -r "async def" src/ | wc -l
364  # 총 364개의 async 함수
```

**비동기 작업 분류**:
- 스케줄러: 3개 (백업, 감사 로그, 질문 풀)
- 백그라운드 태스크: 1개 (리인덱싱)
- 웹훅/알림: 2개 (보안 이벤트, 알림)
- 인덱스 정리: 1개
- **동기 블로킹 작업**: 문서 처리, 임베딩 생성

---

## 🎯 작업 큐 도입이 필요한 이유

### 1. 장시간 실행 작업 (Long-running Tasks)

다음 작업들은 작업 큐로 이동해야 합니다:

#### A. 문서 처리 및 임베딩 생성
**현재 위치**: `src/web_server.py:5343-5356`

```python
# 현재: 동기 처리 (블로킹)
chunks = doc_processor.process_document(str(file_path))  # 10초 ~ 수분
embeddings = embedding_model.encode(texts, batch_size=32)  # 1초 ~ 수십초
```

**예상 처리 시간**:
- 소형 PDF (10페이지): 5-10초
- 중형 PDF (100페이지): 30-60초
- 대형 PDF (500페이지): 2-5분
- HWP/HWPX (변환 포함): +20-30초

**문제**:
- 사용자가 전체 처리 완료까지 대기
- API 타임아웃 위험 (60초 기본값)
- 동시 업로드 제한 (병렬 처리 불가)

#### B. 전체 리인덱싱
**현재 위치**: `src/web_server.py:4656`

```python
# 현재: BackgroundTasks 사용
background_tasks.add_task(run_reindex_task)
```

**예상 처리 시간**:
- 100개 문서: 5-10분
- 1,000개 문서: 30-60분
- 10,000개 문서: 3-5시간

**문제**:
- 서버 재시작 시 작업 손실
- 작업 재시도 메커니즘 없음
- 분산 처리 불가 (단일 서버)

#### C. 대량 그룹 할당
**현재 위치**: `src/group_manager.py`

```python
# 현재: 동기 처리
for doc_id in document_ids:
    assign_group(doc_id, group_id)
```

**예상 처리 시간**:
- 100개 문서: 5-10초
- 1,000개 문서: 30-60초
- 10,000개 문서: 5-10분

### 2. 재시도 및 복구 필요성

다음 작업들은 실패 시 자동 재시도가 필요합니다:

- **웹훅 전송**: 외부 API 호출 실패 시 재시도
- **보안 알림**: 이메일/SMS 전송 실패 시 재시도
- **백업 작업**: 네트워크 오류 시 재시도
- **문서 처리**: 일시적 오류 시 재시도

### 3. 작업 우선순위 및 스케줄링

다음 작업들은 우선순위 관리가 필요합니다:

- **높음**: 보안 알림, 사용자 대기 중인 문서 처리
- **중간**: 리인덱싱, 그룹 할당
- **낮음**: 백업, 로그 정리, 통계 수집

### 4. 수평 확장성 (Horizontal Scaling)

현재 문제:
- 단일 서버에서만 작업 처리
- 부하 분산 불가
- 고가용성 부족

작업 큐 도입 시:
- 여러 워커 서버에서 작업 분산 처리
- 서버 추가로 처리량 증가
- 워커 장애 시 다른 워커로 자동 이관

---

## 💡 권장 솔루션: Celery

### 1. Celery 선택 이유

| 특징 | Celery | RQ | 현재 방식 |
|------|--------|-----|----------|
| Redis 통합 | ✅ Excellent | ✅ Excellent | ⚠️ Basic |
| 재시도 메커니즘 | ✅ Built-in | ⚠️ Limited | ❌ None |
| 스케줄링 | ✅ Celery Beat | ❌ None | ⚠️ Custom |
| 우선순위 큐 | ✅ Yes | ⚠️ Limited | ❌ None |
| 모니터링 | ✅ Flower | ⚠️ Basic | ❌ None |
| 분산 처리 | ✅ Yes | ✅ Yes | ❌ None |
| 학습 곡선 | ⚠️ Medium | ✅ Easy | ✅ Easy |
| 성능 | ✅ Excellent | ✅ Good | ⚠️ Variable |

**결론**: Celery가 엔터프라이즈급 기능과 확장성을 제공하며, 기존 Redis 인프라를 활용할 수 있습니다.

### 2. 구현 아키텍처

```
┌─────────────┐
│  FastAPI    │ ← 사용자 요청
│  Web Server │
└──────┬──────┘
       │ 1. 작업 생성
       ↓
┌─────────────┐
│   Redis     │ ← 메시지 브로커
│  (Broker)   │
└──────┬──────┘
       │ 2. 작업 큐잉
       ↓
┌─────────────┐
│   Celery    │ ← 작업 처리
│   Workers   │
└──────┬──────┘
       │ 3. 결과 저장
       ↓
┌─────────────┐
│   Redis     │ ← 결과 백엔드
│  (Backend)  │
└─────────────┘
```

### 3. 구현 예시

#### A. 의존성 추가
**파일**: `requirements.txt`

```txt
celery[redis]==5.3.4
flower==2.0.1  # 모니터링 대시보드
```

#### B. Celery 앱 설정
**파일**: `src/celery_app.py` (신규 생성)

```python
"""
Celery 애플리케이션 설정
"""
from celery import Celery
from celery.schedules import crontab
import os

# Redis 연결 설정
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Celery 앱 생성
celery_app = Celery(
    "chatbot_tasks",
    broker=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
    backend=f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
    include=['src.tasks']
)

# Celery 설정
celery_app.conf.update(
    # 작업 설정
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Seoul',
    enable_utc=True,

    # 재시도 설정
    task_acks_late=True,  # 작업 완료 후 ack
    task_reject_on_worker_lost=True,
    task_track_started=True,

    # 우선순위 큐 (0-9, 9가 가장 높음)
    task_queue_max_priority=10,
    task_default_priority=5,

    # 결과 보관 기간
    result_expires=3600,  # 1시간

    # 워커 설정
    worker_prefetch_multiplier=4,
    worker_max_tasks_per_child=1000,

    # 스케줄링 (Celery Beat)
    beat_schedule={
        'backup-every-day': {
            'task': 'src.tasks.backup_task',
            'schedule': crontab(hour=2, minute=0),  # 매일 새벽 2시
        },
        'cleanup-audit-logs': {
            'task': 'src.tasks.cleanup_audit_logs_task',
            'schedule': crontab(hour=3, minute=0),  # 매일 새벽 3시
        },
        'cleanup-old-indexes': {
            'task': 'src.tasks.cleanup_old_indexes_task',
            'schedule': crontab(hour=4, minute=0),  # 매일 새벽 4시
        },
    },
)
```

#### C. 작업 정의
**파일**: `src/tasks.py` (신규 생성)

```python
"""
Celery 작업 정의
"""
from celery import Task
from .celery_app import celery_app
from .document_processor import DocumentProcessor
from .embeddings import EmbeddingModel
from .vector_db import VectorDB
from loguru import logger
import time

# 커스텀 베이스 태스크 (재시도 로직)
class BaseTask(Task):
    autoretry_for = (Exception,)
    retry_kwargs = {'max_retries': 3}
    retry_backoff = True
    retry_backoff_max = 600  # 10분
    retry_jitter = True


@celery_app.task(base=BaseTask, bind=True, name='src.tasks.process_document_task')
def process_document_task(self, file_path: str, filename: str, username: str):
    """
    문서 처리 및 임베딩 생성 작업

    Args:
        self: Celery task instance
        file_path: 처리할 파일 경로
        filename: 파일명
        username: 업로드한 사용자

    Returns:
        dict: 처리 결과 (chunk_count, success, etc.)
    """
    try:
        # 진행 상황 업데이트
        self.update_state(
            state='PROCESSING',
            meta={'status': '문서 분석 중...', 'progress': 10}
        )

        # 문서 처리
        doc_processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)
        chunks = doc_processor.process_document(file_path)

        if not chunks:
            raise ValueError(f"No chunks extracted from {filename}")

        self.update_state(
            state='PROCESSING',
            meta={'status': f'임베딩 생성 중... ({len(chunks)} chunks)', 'progress': 50}
        )

        # 임베딩 생성
        embedding_model = EmbeddingModel()
        texts = [chunk["text"] for chunk in chunks]
        embeddings = embedding_model.encode(texts, batch_size=32)

        self.update_state(
            state='PROCESSING',
            meta={'status': '벡터 DB 저장 중...', 'progress': 80}
        )

        # 벡터 DB 저장
        vector_db = VectorDB()
        vector_db.add_documents(
            texts=texts,
            embeddings=embeddings,
            metadatas=[{"filename": filename, "page": c.get("page", 0)} for c in chunks]
        )

        logger.success(f"✅ Document processed successfully: {filename} ({len(chunks)} chunks)")

        return {
            'success': True,
            'filename': filename,
            'chunk_count': len(chunks),
            'username': username,
            'processing_time': self.request.time_elapsed
        }

    except Exception as e:
        logger.error(f"❌ Failed to process document {filename}: {e}")
        raise self.retry(exc=e)


@celery_app.task(base=BaseTask, bind=True, name='src.tasks.reindex_all_task')
def reindex_all_task(self):
    """
    전체 문서 리인덱싱 작업

    Returns:
        dict: 리인덱싱 결과
    """
    try:
        # 구현은 기존 run_reindex_task 로직 사용
        from .web_server import run_reindex_task

        self.update_state(
            state='PROCESSING',
            meta={'status': '리인덱싱 시작...', 'progress': 0}
        )

        result = run_reindex_task()

        logger.success(f"✅ Reindexing completed")
        return result

    except Exception as e:
        logger.error(f"❌ Reindexing failed: {e}")
        raise self.retry(exc=e)


@celery_app.task(name='src.tasks.send_webhook_task')
def send_webhook_task(url: str, data: dict, max_retries: int = 3):
    """
    웹훅 전송 작업 (재시도 포함)

    Args:
        url: 웹훅 URL
        data: 전송할 데이터
        max_retries: 최대 재시도 횟수
    """
    import httpx

    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, json=data)
                response.raise_for_status()
                logger.success(f"✅ Webhook sent successfully: {url}")
                return {'success': True, 'attempt': attempt + 1}
        except Exception as e:
            logger.warning(f"⚠️ Webhook attempt {attempt + 1} failed: {e}")
            if attempt == max_retries - 1:
                logger.error(f"❌ Webhook failed after {max_retries} attempts: {url}")
                raise


@celery_app.task(name='src.tasks.backup_task')
def backup_task():
    """백업 작업 (스케줄러에서 호출)"""
    from .web_server import backup_scheduler
    import asyncio
    asyncio.run(backup_scheduler())


@celery_app.task(name='src.tasks.cleanup_audit_logs_task')
def cleanup_audit_logs_task():
    """감사 로그 정리 작업"""
    from .auth.security_logger import AuditLogger
    audit_logger = AuditLogger()
    deleted_count = audit_logger.cleanup_old_logs()
    logger.info(f"🗑️ Cleaned up {deleted_count} old audit logs")
    return {'deleted_count': deleted_count}


@celery_app.task(name='src.tasks.cleanup_old_indexes_task')
def cleanup_old_indexes_task():
    """오래된 인덱스 정리 작업"""
    from .vector_db import VectorDB
    vector_db = VectorDB()
    # 구현 필요: 7일 이상 된 비활성 인덱스 삭제
    pass
```

#### D. FastAPI 통합
**파일**: `src/web_server.py` (수정)

```python
from .tasks import process_document_task, reindex_all_task

@app.post("/api/upload", tags=["Documents"])
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user)
):
    """문서 업로드 (비동기 처리)"""
    try:
        # 파일 저장 (동기)
        safe_filename = validate_filename(file.filename)
        file_path = save_uploaded_file(file, safe_filename)

        # Celery 작업 큐에 추가 (비동기)
        task = process_document_task.apply_async(
            args=[str(file_path), safe_filename, current_user['username']],
            priority=7  # 높은 우선순위
        )

        return {
            "message": "문서 처리가 시작되었습니다",
            "filename": safe_filename,
            "task_id": task.id,
            "status_url": f"/api/task/{task.id}"
        }

    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/task/{task_id}", tags=["Tasks"])
async def get_task_status(task_id: str):
    """작업 상태 조회"""
    from .celery_app import celery_app

    task = celery_app.AsyncResult(task_id)

    if task.state == 'PENDING':
        response = {'state': task.state, 'status': '대기 중...'}
    elif task.state == 'PROCESSING':
        response = {
            'state': task.state,
            'status': task.info.get('status', ''),
            'progress': task.info.get('progress', 0)
        }
    elif task.state == 'SUCCESS':
        response = {
            'state': task.state,
            'result': task.info
        }
    elif task.state == 'FAILURE':
        response = {
            'state': task.state,
            'error': str(task.info)
        }
    else:
        response = {'state': task.state}

    return response


@app.post("/api/reindex", tags=["Documents"])
async def reindex(
    current_user: dict = Depends(get_current_active_user)
):
    """전체 리인덱싱 (비동기)"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자 권한이 필요합니다")

    task = reindex_all_task.apply_async(priority=5)

    return {
        "message": "리인덱싱이 시작되었습니다",
        "task_id": task.id,
        "status_url": f"/api/task/{task.id}"
    }
```

#### E. 워커 실행
**파일**: `docker-compose.yml` (추가)

```yaml
services:
  # ... 기존 서비스 ...

  celery-worker:
    build: .
    container_name: chatbot_celery_worker
    command: celery -A src.celery_app worker --loglevel=info --concurrency=4
    volumes:
      - ./data:/app/data
      - ./models:/app/models
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 4G

  celery-beat:
    build: .
    container_name: chatbot_celery_beat
    command: celery -A src.celery_app beat --loglevel=info
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    restart: unless-stopped

  flower:
    build: .
    container_name: chatbot_flower
    command: celery -A src.celery_app flower --port=5555
    ports:
      - "5555:5555"
    environment:
      - REDIS_HOST=redis
      - REDIS_PORT=6379
    depends_on:
      - redis
    restart: unless-stopped
```

---

## 📊 예상 효과

### 1. 성능 개선

| 작업 | 현재 (동기) | Celery 적용 후 | 개선율 |
|------|------------|---------------|--------|
| 문서 업로드 API 응답 | 10-60초 | <1초 | **95%+** |
| 동시 업로드 처리 | 1개 | 4-8개 (워커 수) | **400-800%** |
| 리인덱싱 중 서버 응답성 | 느림 | 정상 | **100%** |
| 작업 실패 시 복구 | 수동 | 자동 (3회 재시도) | **자동화** |

### 2. 사용자 경험 개선

**현재**:
- ❌ 대용량 파일 업로드 시 오래 대기
- ❌ 타임아웃 오류 발생
- ❌ 작업 진행 상황 확인 불가

**개선 후**:
- ✅ 즉시 응답 (<1초)
- ✅ 백그라운드에서 안정적 처리
- ✅ 실시간 진행 상황 확인 가능
- ✅ 작업 완료 알림

### 3. 시스템 안정성 개선

**현재 문제**:
- 서버 재시작 시 진행 중인 작업 손실
- 작업 실패 시 수동 재처리 필요
- 부하 분산 불가

**개선 효과**:
- 작업 큐에 보관되어 재시작 후에도 처리
- 자동 재시도 (최대 3회)
- 여러 워커로 부하 분산

---

## 🚀 구현 로드맵

### Phase 1: 기본 설정 (1-2일)
- [x] Celery 및 Flower 설치
- [ ] `src/celery_app.py` 생성
- [ ] Docker Compose에 워커 추가
- [ ] 기본 작업 테스트

### Phase 2: 핵심 작업 이전 (3-5일)
- [ ] 문서 처리 작업 (`process_document_task`)
- [ ] 리인덱싱 작업 (`reindex_all_task`)
- [ ] 작업 상태 API (`/api/task/{task_id}`)
- [ ] 웹훅 작업 (`send_webhook_task`)

### Phase 3: 스케줄러 이전 (1-2일)
- [ ] 백업 작업 Celery Beat으로 이전
- [ ] 감사 로그 정리 작업 이전
- [ ] 인덱스 정리 작업 이전
- [ ] 기존 asyncio 스케줄러 제거

### Phase 4: 모니터링 및 최적화 (2-3일)
- [ ] Flower 대시보드 설정
- [ ] 작업 메트릭 수집
- [ ] 우선순위 튜닝
- [ ] 워커 수 최적화
- [ ] 성능 테스트

### 총 예상 기간: **7-12일**

---

## ⚠️ 주의사항 및 제약사항

### 1. 복잡도 증가
- Celery 설정 및 운영 학습 필요
- 추가 컨테이너 관리 (worker, beat, flower)
- 디버깅 복잡도 증가 (분산 환경)

### 2. 리소스 요구사항
- 워커 프로세스 추가 메모리: 500MB-1GB per worker
- Redis 메모리 증가: 작업 큐 및 결과 저장
- CPU: 워커 수만큼 코어 권장

### 3. 개발 환경 설정
- 로컬 개발 시 Celery 워커 실행 필요
- 테스트 시 비동기 작업 처리 방식 변경 필요
- 디버깅 도구 및 프로세스 수정

### 4. 마이그레이션 위험
- 기존 작업 처리 로직 변경 필요
- 이전 중 일부 작업 손실 가능
- 롤백 계획 필수

---

## 🎯 결론 및 권장사항

### 즉시 실행 권장 (High Priority)
1. **문서 업로드 처리**: 사용자 경험 개선 효과가 크고, 타임아웃 문제 해결
2. **리인덱싱 작업**: 서버 재시작 시 작업 손실 방지

### 중기 실행 권장 (Medium Priority)
3. **스케줄러 이전**: Celery Beat으로 통합하여 관리 단순화
4. **웹훅/알림 작업**: 재시도 메커니즘 통한 안정성 향상

### 장기 실행 권장 (Low Priority)
5. **대량 작업 처리**: 그룹 할당, 벌크 업데이트 등
6. **통계 수집 작업**: 백그라운드 집계 및 보고서 생성

### 최종 권장사항

**현재 시스템 규모와 사용 패턴을 고려할 때, Celery 도입을 강력히 권장합니다:**

✅ **즉시 도입 권장**:
- 문서 업로드 API가 타임아웃 문제를 겪고 있거나
- 대용량 파일 처리가 필요하거나
- 여러 사용자의 동시 업로드가 예상되는 경우

⏸️ **Phase 2로 연기 가능**:
- 현재 단일 사용자 또는 소규모 문서만 처리 중이고
- API 타임아웃 문제가 없으며
- 시스템 복잡도 증가를 피하고 싶은 경우

**단, 향후 다음과 같은 상황이 발생하면 즉시 Celery 도입을 검토해야 합니다:**
- 문서 업로드 API 타임아웃 발생
- 리인덱싱 중 서버 재시작으로 작업 손실
- 동시 업로드 요청 증가
- 시스템 확장 필요성 대두

---

## 📚 참고 자료

- [Celery 공식 문서](https://docs.celeryq.dev/)
- [Celery Best Practices](https://docs.celeryq.dev/en/stable/userguide/tasks.html#best-practices)
- [Flower 모니터링](https://flower.readthedocs.io/)
- [Redis as Celery Broker](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html)
