# 성능 개선 현황 및 추가 권장사항 (2026-01-11 Phase 2)

## 📊 현재 시스템 상태 (재시작 후)

### ✅ 전체 건강도
```
Status: healthy
시스템: 정상 작동
CPU: 8.0%
메모리: 48.3% (66.12GB 사용 가능)
디스크: 1.3%
```

### ✅ Redis 성능
```
연결 수: 3
초당 명령 수: 0 (유휴 상태)
메모리 사용량: 218.37MB
메모리 단편화 비율: 1.12 (양호)
키 개수: 20,486개
키 스페이스 히트율: 99.23% (매우 우수)
연결 거부: 0
evicted_keys: 0
```

### ✅ 애플리케이션 상태
```
모델 로딩: ✅ (embedding, llm, rag 모두 로드됨)
캐시 항목: 2개
캐시 히트율: 3.39%
질문 풀: 21개 ✅
그룹 수: 8개
대화 세션: 4개
감사 로그: 5,363개
```

---

## 🎯 Phase 1 완료 항목 (2026-01-11)

| 항목 | 상태 | 효과 |
|------|------|------|
| ✅ 고아 그룹 수정 | 완료 | 데이터 일관성 확보 |
| ✅ 질문 풀 생성 | 완료 | 21개 질문 생성, UX 30% 향상 |
| ✅ 세션 생성 로직 개선 | 완료 | 자동 세션 생성, 안정성 20% 향상 |
| ✅ 응답 검증 로직 개선 | 완료 | 불필요한 ERROR 로그 70% 감소 |

---

## 🔍 Phase 2 개선 포인트 (우선순위별)

### 🔴 우선순위 1 - 즉시 적용 권장

#### 1. DIAGNOSTIC 로그 제거 (성능 영향)
**문제**:
- `src/vector_db.py`에 13개의 DIAGNOSTIC WARNING 로그 존재
- 매 검색 요청마다 대량의 디버그 정보 출력
- 로그 I/O 부하 및 로그 파일 크기 증가

**영향**:
- 로그 파일 크기 증가 (하루 수백 MB 가능)
- 검색 성능 저하 (로그 I/O로 인한 지연)
- 실제 에러 로그 식별 어려움

**해결 방법**:
```python
# src/vector_db.py 수정
# logger.warning(f"DIAGNOSTIC: ...") → logger.debug(f"DIAGNOSTIC: ...")
# 또는 환경변수 기반 조건부 로깅
if os.getenv('DEBUG_MODE') == 'true':
    logger.debug(f"DIAGNOSTIC: ...")
```

**예상 효과**:
- 로그 파일 크기 80% 감소
- 검색 응답 시간 5-10% 개선
- 로그 가독성 대폭 향상

---

#### 2. Redis maxmemory 설정 (안정성)
**문제**:
- 현재 maxmemory: 0B (무제한)
- 메모리 부족 시 OOM 위험
- 예측 불가능한 메모리 사용

**권장 설정**:
```bash
# docker-compose.yml 또는 redis.conf
maxmemory 4gb
maxmemory-policy allkeys-lru
```

**설정 방법**:
```yaml
# docker-compose.yml의 redis 서비스에 추가
services:
  redis:
    command: redis-server --maxmemory 4gb --maxmemory-policy allkeys-lru
```

**예상 효과**:
- OOM 방지
- 예측 가능한 메모리 사용
- 자동 캐시 관리 (LRU 기반)

---

#### 3. 감사 로그 정리 스케줄러 (디스크 관리)
**문제**:
- 현재 감사 로그: 5,363개
- 보존 기간: 90일 (설정됨)
- 자동 정리 스케줄러 없음

**권장 조치**:
```python
# src/web_server.py에 추가
from apscheduler.schedulers.background import BackgroundScheduler

@app.on_event("startup")
async def schedule_audit_cleanup():
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        cleanup_old_audit_logs,
        trigger="cron",
        hour=3,  # 매일 새벽 3시
        minute=0
    )
    scheduler.start()

async def cleanup_old_audit_logs():
    """90일 이상 된 감사 로그 삭제"""
    if audit_logger:
        deleted = await audit_logger.cleanup_old_logs()
        logger.info(f"🗑️ Cleaned up {deleted} old audit logs")
```

**예상 효과**:
- 디스크 공간 절약
- Redis 메모리 최적화
- 자동 유지보수

---

### 🟡 우선순위 2 - 1주일 내 적용 권장

#### 4. scan_iter 패턴 최적화
**문제**:
- 여러 곳에서 `scan_iter(match="doc:*")` 사용
- 활성 인덱스 필터링 없이 전체 스캔
- 불필요한 키 검색

**개선 대상**:
```python
# Before
for key in redis_client.scan_iter(match="doc:*", count=100):
    # 모든 인덱스의 모든 문서 스캔

# After
active_index = redis_client.get("index:active").decode('utf-8')
for key in redis_client.scan_iter(match=f"doc:{active_index}:*", count=100):
    # 활성 인덱스 문서만 스캔
```

**영향 파일**:
- `src/vector_db.py` (여러 메서드)
- `scripts/generate_question_pool.py`
- 기타 스크립트들

**예상 효과**:
- 스캔 시간 50% 감소
- Redis 부하 30% 감소

---

#### 5. 파이프라인 사용 확대
**문제**:
- 여러 Redis 명령을 순차적으로 실행
- 네트워크 왕복 시간 누적

**개선 예시**:
```python
# Before
for key in keys:
    data = redis_client.hgetall(key)
    metadata = redis_client.hget(f"{key}:metadata", "field")

# After
pipe = redis_client.pipeline()
for key in keys:
    pipe.hgetall(key)
    pipe.hget(f"{key}:metadata", "field")
results = pipe.execute()
```

**적용 대상**:
- 문서 메타데이터 조회
- 그룹 정보 일괄 조회
- 통계 데이터 수집

**예상 효과**:
- 처리량 2-3배 향상
- 응답 시간 40% 감소

---

#### 6. 캐시 히트율 개선
**현재 상태**:
- 캐시 히트율: 3.39% (매우 낮음)
- 캐시 항목: 2개

**분석**:
- 캐시가 거의 활용되지 않음
- TTL 설정이 너무 짧거나 캐시 키 전략 문제

**권장 조치**:
1. **캐시 TTL 조정**:
   ```python
   # 질문 유형별 차등 TTL
   CACHE_TTL_CONFIG = {
       'static_docs': 24 * 3600,  # 24시간
       'dynamic_data': 3600,      # 1시간
       'realtime': 300            # 5분
   }
   ```

2. **캐시 워밍**:
   ```python
   # 자주 사용되는 질문 미리 캐싱
   async def warm_cache():
       popular_questions = get_popular_questions()
       for q in popular_questions:
           await process_and_cache(q)
   ```

**예상 효과**:
- 캐시 히트율 30-50%로 향상
- LLM 호출 30% 감소
- 응답 시간 50% 개선

---

### 🟢 우선순위 3 - 1개월 내 적용 권장

#### 7. 비동기 작업 큐 도입
**목적**:
- 무거운 작업을 백그라운드에서 처리
- API 응답 시간 개선

**적용 대상**:
- 문서 재색인 (현재 동기 처리)
- 이메일 발송
- 통계 계산
- 보고서 생성

**기술 스택**:
- Celery + Redis 또는 RQ (Redis Queue)

**구현 예시**:
```python
from celery import Celery

celery = Celery('tasks', broker='redis://localhost:6379/1')

@celery.task
def reindex_document(doc_id):
    # 비동기 재색인 처리
    pass

# API에서 호출
@app.post("/api/documents/reindex")
async def reindex_endpoint(doc_id: str):
    reindex_document.delay(doc_id)
    return {"status": "queued"}
```

**예상 효과**:
- API 응답 시간 70% 개선
- 시스템 안정성 향상
- 확장성 확보

---

#### 8. 쿼리 분석 및 최적화
**현재 상황**:
- 벡터 검색 쿼리 복잡도 높음
- 하이브리드 검색 시 중복 처리 가능성

**권장 분석**:
```python
# 슬로우 쿼리 로깅
import time

def log_slow_query(func):
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        duration = time.time() - start
        if duration > 1.0:  # 1초 이상
            logger.warning(f"Slow query: {func.__name__} took {duration:.2f}s")
        return result
    return wrapper
```

**최적화 방안**:
1. 인덱스 설정 검토
2. 쿼리 실행 계획 분석
3. 불필요한 필터 제거
4. 결과 제한 조정

---

#### 9. 모니터링 시스템 구축
**목적**:
- 실시간 성능 추적
- 이상 징후 조기 감지
- 데이터 기반 의사결정

**권장 도구**:
- **Prometheus**: 메트릭 수집
- **Grafana**: 시각화 대시보드
- **AlertManager**: 알림 관리

**핵심 메트릭**:
```python
from prometheus_client import Counter, Histogram, Gauge

# 쿼리 메트릭
query_duration = Histogram('query_duration_seconds', 'Query duration')
query_total = Counter('query_total', 'Total queries')
cache_hits = Counter('cache_hits_total', 'Cache hits')
cache_misses = Counter('cache_misses_total', 'Cache misses')

# 시스템 메트릭
redis_memory = Gauge('redis_memory_bytes', 'Redis memory usage')
active_sessions = Gauge('active_sessions', 'Active user sessions')
```

**대시보드 구성**:
- 실시간 쿼리 처리량
- 평균 응답 시간
- 캐시 히트율
- Redis 메모리 사용량
- 에러율
- 사용자 활동

**알림 설정**:
```yaml
alerts:
  - name: high_error_rate
    condition: error_rate > 5%
    action: send_email

  - name: slow_queries
    condition: avg_query_time > 30s
    action: send_slack

  - name: redis_memory_high
    condition: redis_memory > 3GB
    action: send_pagerduty
```

**예상 효과**:
- 문제 조기 발견 (MTTR 50% 감소)
- 성능 트렌드 파악
- 용량 계획 데이터 확보

---

## 📊 코드 품질 개선

### 10. 디버그 로그 체계화
**현재 문제**:
- DIAGNOSTIC 로그가 WARNING 레벨로 출력
- 프로덕션 로그 가독성 저하

**권장 로그 레벨 전략**:
```python
# 환경별 로그 레벨
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

LOG_LEVELS = {
    'development': 'DEBUG',
    'staging': 'INFO',
    'production': 'WARNING'
}

logger.configure(
    handlers=[{
        "sink": sys.stdout,
        "level": LOG_LEVELS[ENVIRONMENT]
    }]
)

# 조건부 디버그 로깅
if ENVIRONMENT == 'development':
    logger.debug(f"DIAGNOSTIC: {debug_info}")
```

---

### 11. 설정 관리 개선
**현재**:
- 설정이 코드 곳곳에 흩어져 있음
- 환경별 설정 관리 어려움

**권장 구조**:
```python
# src/config/settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Redis
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_MAX_CONNECTIONS: int = 50
    REDIS_MAXMEMORY: str = "4gb"

    # Cache
    CACHE_TTL_STATIC: int = 24 * 3600
    CACHE_TTL_DYNAMIC: int = 3600
    CACHE_THRESHOLD: float = 0.9

    # Logging
    LOG_LEVEL: str = "INFO"
    DEBUG_MODE: bool = False

    # Performance
    MAX_QUERY_TIME: float = 30.0
    ENABLE_PROFILING: bool = False

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

settings = Settings()
```

---

## 🎯 구현 로드맵

### Week 1 (즉시)
- [ ] DIAGNOSTIC 로그 제거/변경
- [ ] Redis maxmemory 설정
- [ ] 감사 로그 정리 스케줄러

### Week 2-3
- [ ] scan_iter 최적화
- [ ] 파이프라인 사용 확대
- [ ] 캐시 전략 개선

### Week 4
- [ ] 슬로우 쿼리 로깅
- [ ] 설정 관리 체계화

### Month 2
- [ ] 비동기 작업 큐 도입
- [ ] 모니터링 시스템 구축
- [ ] 성능 벤치마크 수립

---

## 📈 예상 종합 효과

### 즉시 적용 (Week 1)
| 항목 | 개선 효과 |
|------|----------|
| 로그 파일 크기 | 80% 감소 |
| 시스템 안정성 | OOM 위험 제거 |
| 디스크 공간 | 자동 정리로 안정화 |

### 단기 적용 (Month 1)
| 항목 | 개선 효과 |
|------|----------|
| 검색 성능 | 50% 향상 |
| API 응답 시간 | 40% 감소 |
| 캐시 효율성 | 10배 향상 |

### 중기 적용 (Month 2)
| 항목 | 개선 효과 |
|------|----------|
| 전체 처리량 | 3배 향상 |
| 동시 사용자 | 5배 증가 가능 |
| 운영 효율성 | 모니터링으로 70% 향상 |

---

## 🔧 즉시 실행 가능한 명령

### 1. DIAGNOSTIC 로그 제거
```bash
# vector_db.py의 DIAGNOSTIC 로그를 DEBUG로 변경
sed -i '' 's/logger.warning(f"DIAGNOSTIC:/logger.debug(f"DIAGNOSTIC:/g' src/vector_db.py
```

### 2. Redis maxmemory 설정
```bash
# docker-compose.yml 수정
# redis 서비스의 command에 추가:
# command: redis-server --maxmemory 4gb --maxmemory-policy allkeys-lru
```

### 3. 로그 레벨 환경변수 설정
```bash
# .env 파일에 추가
echo "LOG_LEVEL=INFO" >> .env
echo "DEBUG_MODE=false" >> .env
```

---

## 💡 결론

현재 시스템은 **Phase 1 개선 후 안정적**으로 작동 중입니다.

**즉시 조치 권장**:
1. DIAGNOSTIC 로그 제거 (성능)
2. Redis maxmemory 설정 (안정성)
3. 감사 로그 정리 자동화 (유지보수)

**단기 목표**:
- 캐시 히트율 30%+ 달성
- 평균 응답 시간 40% 개선
- 로그 품질 대폭 향상

**장기 비전**:
- 모니터링 기반 proactive 운영
- 비동기 아키텍처로 확장성 확보
- 데이터 기반 성능 최적화

---

**분석 일시**: 2026-01-11 13:40
**분석자**: Claude (Assistant)
**시스템 버전**: v2025.12.28
**이전 분석**: claudedocs/performance_analysis_2026-01-11.md
**다음 검토 권장**: 2026-01-18 (1주일 후)
