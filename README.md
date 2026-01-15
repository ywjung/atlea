# 📚 문서 RAG 챗봇 (Document RAG Chatbot)

<div align="center">

**AI 기반 문서 질의응답 시스템**

다양한 형식의 문서를 이해하고 자연어로 질문에 답변하는 인텔리전트 챗봇

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Java](https://img.shields.io/badge/Java-21-orange.svg)](https://openjdk.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com/)
[![Redis](https://img.shields.io/badge/Redis-Stack-red.svg)](https://redis.io/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[빠른 시작](#-빠른-시작) • [기능](#-주요-기능) • [문서](#-사용-가이드) • [API](#-api-레퍼런스) • [개발](#-개발자-가이드)

</div>

---

## 📖 목차

- [최근 업데이트](#-최근-업데이트-2026-01-02)
- [소개](#-소개)
- [주요 기능](#-주요-기능)
- [시스템 아키텍처](#-시스템-아키텍처)
- [기술 스택](#-기술-스택)
- [시스템 요구사항](#-시스템-요구사항)
- [빠른 시작](#-빠른-시작)
- [사용 가이드](#-사용-가이드)
- [API 레퍼런스](#-api-레퍼런스)
- [개발자 가이드](#-개발자-가이드)
- [환경 설정](#-환경-설정)
- [성능 최적화](#-성능-최적화)
- [문제 해결](#-문제-해결)
- [배포 가이드](#-배포-가이드)
- [보안](#-보안)
- [로드맵](#%EF%B8%8F-로드맵)
- [기여 가이드](#-기여-가이드)
- [FAQ](#-faq)
- [라이선스](#-라이선스)

---

## 🆕 최근 업데이트 (2026-01-02)

### 🔐 인증 및 보안 시스템 (v2.4.0)

#### JWT 기반 인증
- **Access/Refresh Token**: 15분 액세스 토큰 + 7일 리프레시 토큰
- **자동 갱신**: 토큰 만료 전 자동 갱신으로 끊김 없는 사용
- **세션 관리**: Redis 기반 세션 추적 및 관리
- **브루트포스 방어**: 5회 실패 시 계정 잠금 (30분)

#### TOTP 2단계 인증
- **Google Authenticator 호환**: 표준 TOTP 프로토콜 지원
- **QR 코드 등록**: 간편한 설정 프로세스
- **복구 코드**: 기기 분실 시 복구 수단 제공
- **선택적 활성화**: 사용자별 2FA 활성화/비활성화

#### 비밀번호 재설정
- **이메일 토큰**: 안전한 토큰 기반 재설정
- **복잡도 검증**: 8자 이상, 대소문자/숫자/특수문자 포함
- **실시간 검증**: 프론트엔드에서 즉시 피드백
- **토큰 만료**: 15분 유효기간으로 보안 강화

### 🏢 조직 기반 접근 제어 (v2.4.0)

#### Multi-Tenant 아키텍처
- **조직 관리**: 독립적인 조직별 데이터 격리
- **사용자-조직 매핑**: 1:1 관계로 명확한 소속 구조
- **조직-그룹-문서**: 계층적 권한 체계

#### 권한 체계
- **시스템 관리자**: 모든 조직 접근 및 관리
- **조직 관리자**: 소속 조직 내 사용자/문서 관리
- **일반 사용자**: 소속 조직 문서만 검색 및 조회

#### 데이터 격리
- **문서 필터링**: 조직별 자동 필터링으로 데이터 누수 방지
- **검색 권한**: 벡터 검색 시 조직 권한 자동 적용
- **그룹 관리**: 조직별 독립적인 그룹 구조

### 📚 문서 버전 관리 (v2.3.0)

#### 자동 버전 관리
- **버전 추적**: 파일 업로드 시 자동 버전 생성 (v1, v2, v3...)
- **해시 기반 중복 감지**: MD5 해시로 동일 파일 감지
- **메타데이터 저장**: 업로드 시간, 사용자, 파일 크기, 청크 수

#### 버전 비교 및 복원
- **버전 목록 조회**: 문서별 모든 버전 히스토리 확인
- **버전 복원**: 이전 버전으로 롤백 기능
- **삭제 보호**: 최신 버전 외 이전 버전 보관

#### UI 개선
- **중복 파일 경고**: 동일 파일 업로드 시 주황색 경고 메시지 (5초)
- **버전 표시**: 문서 목록에서 버전 정보 표시
- **청크 뷰어**: 버전별 청크 내용 확인 가능

### 🛡️ 보안 강화 (v2.4.0)

#### SBOM 및 취약점 스캔
- **자동 스캔**: 설치 시 의존성 취약점 자동 검사
- **SBOM 생성**: CycloneDX 형식 SBOM 생성
- **취약점 보고서**: pip-audit로 Python 패키지 검사
- **통합 관리**: 단일 스크립트로 보안 검사 자동화

#### 보안 이벤트 로깅
- **이벤트 추적**: 로그인 실패, 계정 잠금, 권한 오류 기록
- **대시보드 표시**: 관리자 페이지에서 최근 보안 이벤트 확인
- **감사 로그**: 주요 보안 이벤트 영구 기록

#### 세션 보안
- **활성 세션 모니터링**: 사용자별 활성 세션 추적
- **강제 로그아웃**: 관리자의 세션 강제 종료 기능
- **세션 만료**: 장기 미사용 세션 자동 정리

### 🐛 최근 버그 수정 (2026-01-02)

#### 시스템 통계 수정
- **24시간 로그인 추적**: 최근 로그인 카운트가 0으로 표시되던 문제 해결
- **타임존 처리**: Z 접미사 유무에 관계없이 정확한 타임스탬프 파싱
- **API 응답 정규화**: `recent_logins_24h` 필드 추가로 프론트엔드 호환성 개선

#### 중복 파일 감지 UI
- **경고 메시지 표시**: 중복 파일 업로드 시 주황색 경고 (기존: 초록색 성공 메시지)
- **사용자 피드백**: 기존 파일명 표시로 명확한 안내
- **자동 숨김**: 5초 후 자동으로 메시지 제거

#### 모달 스크롤 개선
- **청크 뷰어 고정**: 모달 헤더 고정, 청크 내용만 스크롤
- **Flexbox 레이아웃**: 반응형 레이아웃으로 사용성 개선
- **80vh 높이**: 화면 크기에 맞춘 최적 높이 설정

### ✨ 주요 기능 개선 (2025-12-26)

#### 📝 TXT 파일 지원 추가
- **다중 인코딩 처리**: UTF-8, CP949, EUC-KR 자동 감지 및 변환
- **Python 직접 처리**: Java 서비스 없이 경량 처리
- **기존 파이프라인 통합**: 다른 문서와 동일한 색인 및 검색 지원
- 지원 형식: 이제 총 **11가지** (PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT)

#### 🗑️ 전체 대화 삭제 기능
- **일괄 삭제**: 모든 대화 기록을 한 번에 삭제
- **자동 새 대화**: 삭제 후 새로운 대화 자동 생성으로 즉시 사용 가능
- **이중 확인**: 실수 방지를 위한 확인 다이얼로그 (대화 개수 표시)
- **API 엔드포인트**: `DELETE /api/conversations`

#### 🔍 참고문서 상세보기 개선
- **이벤트 위임 패턴**: 동적 생성 요소에 자동 이벤트 연결
- **하이브리드 로딩**: 캐시 우선 + 서버 폴백 전략
- **로딩 인디케이터**: 서버에서 데이터 가져올 때 진행 상태 표시
- **하위 호환성**: 기존 대화와 새 대화 모두 지원

### 🎨 UI/UX 개선

#### 모달 스택 관리
- **LIFO 방식**: ESC 키로 최상위 모달만 닫기
- **중첩 모달 지원**: 문서 관리 → 버전 관리 등 다단계 모달에서 단계별 닫기
- **특수 모달 처리**: 설정, 사이드바 등 고유 동작 유지
- **기술 구현**: 전역 `modalStack` 배열 + Helper 함수 (`pushModal`, `popModal`, `getTopmostModal`, `closeTopmost`)

#### 환영 화면 표시 개선
- **새 대화 시**: 환영 메시지와 추천 질문 자동 표시
- **페이지 새로고침**: 빈 화면 대신 환영 화면 표시
- **코드 중복 제거**: 43줄 HTML 제거, 함수 재사용으로 개선

#### 추천 질문 다양화
- **질문 풀 확대**: 5개 → 30개 다양한 질문
- **무작위 선택**: 새로고침마다 5개 무작위 표시
- **카테고리 분류**: 일반, 상세 분석, 실무, 비교, 구체적 정보, 컨텍스트 등

#### 버그 수정
- **재생성 버튼 오류**: 불러온 대화에서 재생성 시 "질문 없음" 오류 해결
- **스크롤바 스타일링**: 다크 테마에 맞춘 일관된 디자인 적용

### ⚡ 성능 최적화

#### Backend 최적화 (2025-12-25)
- **Health Endpoint**: 116ms → 4.9ms (96% 개선)
  - CPU 모니터링: `interval=0` (즉시 읽기)
  - Redis 체크: `INFO` → `PING` (경량화)
- **Embedding 캐싱**: LRU 1000개 항목, MD5 해시 키
  - 캐시 히트 시 GPU 추론 스킵
  - 중복 쿼리 최적화

#### Frontend 최적화
- **프로덕션 로그 제거**: 15+ console.log 문 정리
  - group-manager.js: 9개 로깅 제거
  - script.js: 6개 로깅 제거
  - DEBUG_MODE 보호 로그만 유지
- **성능 유틸리티 모듈** (`utils.js`):
  - Debounce/Throttle 함수
  - DOM 캐싱 시스템
  - 이벤트 위임
  - 요청 큐 및 배칭
- **최적화 모듈** (`optimizations.js`):
  - Markdown 렌더링 메모이제이션 (LRU 100개)
  - 가상 스크롤링
  - 메시지 객체 풀링
  - 요청 중복 제거
  - Lazy 이미지 로딩
  - localStorage 자동 정리

#### Java API 최적화
- **PDF 추출**: 페이지별 → 단일 패스 알고리즘 (대폭 향상)
- **Caffeine 캐시**: 100 → 500 항목 (5배), TTL 1시간 → 2시간
- **로깅 최적화**: INFO → DEBUG (프로덕션)

#### 성능 벤치마크
| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| Health Check | 116ms | 4.9ms | 96% |
| 중복 쿼리 (캐시) | GPU 추론 | 즉시 응답 | ~99% |
| PDF 추출 (10페이지) | 2.5s | 0.8s | 68% |
| Java 캐시 적중률 | 80% | 90% | +10% |

### 🏗️ 코드 아키텍처

#### JavaScript 모듈화 준비
- **Core 모듈**: `modal-manager.js`, `utils.js` (공통 유틸리티)
- **Feature 모듈**: `chat.js`, `documents.js`, `versions.js`, `settings.js`, `history.js`, `theme.js`
- **아키텍처 문서**: `static/js/ARCHITECTURE.md`, `static/js/README.md`
- **현재 상태**: 구조 설계 완료, 코드 마이그레이션 대기 중 (기존 `script.js` 사용)

#### 성능 모듈 추가
- **utils.js**: 범용 유틸리티 함수 (debounce, throttle, DOM 캐싱)
- **optimizations.js**: 앱 특화 성능 향상 (memoization, 가상 스크롤, 객체 풀링)
- **performance_optimizer.py**: 백엔드 캐싱 및 모니터링

---

## 🎯 소개

### 프로젝트 개요

문서 RAG 챗봇은 **Retrieval-Augmented Generation (RAG)** 기술을 활용하여 다양한 형식의 문서에서 정보를 추출하고, 자연어 질문에 정확하게 답변하는 AI 시스템입니다.

### 주요 사용 사례

- 📄 **기업 문서 관리**: 내부 정책, 매뉴얼, 보고서에서 신속한 정보 검색
- 📚 **연구 자료 분석**: 학술 논문, 기술 문서에서 필요한 정보 추출
- 🏢 **고객 지원**: FAQ, 제품 문서 기반 자동 응답 시스템
- 📖 **교육 자료**: 교재, 강의 노트에서 학습 내용 질의응답
- ⚖️ **법률/규정 검토**: 법률 문서, 규정에서 특정 조항 검색

### 핵심 가치

- ✅ **정확성**: RAG 기반으로 실제 문서 내용에 근거한 답변
- ⚡ **신속성**: 벡터 검색으로 대량 문서에서 밀리초 단위 검색
- 🎨 **사용 편의성**: 직관적인 웹 UI로 누구나 쉽게 사용
- 🔧 **확장성**: 멀티 워커 아키텍처로 동시 다수 사용자 지원
- 🛡️ **안정성**: 프로덕션 레벨 에러 처리 및 모니터링

---

## ✨ 주요 기능

### 🔍 문서 처리 및 검색

#### 다중 형식 지원
- **11가지 문서 형식**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT (신규)
- **파일 크기 제한**: 최대 100MB (설정 가능)
- **Magic Bytes 검증**: 파일 확장자 위조 방지
- **자동 인코딩 감지**: UTF-8, CP949, EUC-KR 등 다양한 인코딩 지원 (TXT 파일)
- **TXT 직접 처리**: Python에서 직접 처리, Java 서비스 불필요

#### 고성능 텍스트 추출
- **Java 추출 서비스**: Apache POI + PDFBox 기반 고성능 엔진
- **단일 패스 PDF 추출**: 페이지별 추출 대비 대폭 향상
- **Caffeine 캐싱**: 500개 항목 LRU 캐시로 99% 빠른 재처리
- **Python Fallback**: Java 서비스 미사용 시 자동 대체

#### 스마트 색인 시스템
- **변경 감지**: MD5 해시 기반 파일 변경 자동 감지
- **증분 색인**: 변경된 파일만 재색인하여 시간 절약
- **메타데이터 추적**: 파일 크기, 수정 시간, 해시값 저장
- **자동 재색인**: 서버 시작 시 변경 파일 자동 감지 및 처리

#### 벡터 검색
- **Redis Vector DB**: RediSearch 기반 고속 벡터 검색
- **코사인 유사도**: 의미적 유사성 기반 검색
- **연결 풀링**: 50개 연결 풀로 5-10배 처리량 향상
- **Top-K 검색**: 설정 가능한 검색 결과 수 (기본 5개)

#### 문서 그룹 관리
- **계층 구조**: 폴더처럼 그룹을 계층적으로 구성
- **메타데이터**: 이름, 설명, 색상, 아이콘으로 그룹 커스터마이징
- **문서 할당**: 드래그 앤 드롭으로 간편한 문서 그룹 지정
- **그룹별 검색**: 특정 그룹 문서만 검색 (OR 조건 지원)
- **순환 방지**: 부모-자식 관계에서 순환 참조 자동 차단

### 🤖 AI 기능

#### 대형 언어 모델 (LLM)
- **Qwen3 30B**: 고성능 다국어 LLM (4-bit 양자화, ~20GB RAM)
  - 기본 설정으로 사용 중인 프로덕션 모델
  - 최고 성능의 한국어 질의응답
- **MLX 프레임워크**: Apple Silicon GPU 가속
- **멀티 플랫폼**: MLX (Mac), CUDA (NVIDIA), CPU 자동 선택
- **스트리밍 응답**: 실시간 토큰 생성 및 표시
- **컨텍스트 윈도우**: 최대 32K 토큰 처리
- **한국어 최적화**: 한국어 질의응답에 특화

#### Embeddings
- **KURE-v1**: Korean Universal Representation Embeddings
- **특화**: 한국어 의미 검색에 최적화된 임베딩 모델
- **차원**: 1024차원 벡터
- **MPS 가속**: Metal Performance Shaders로 GPU 활용
- **배치 처리**: 여러 텍스트 동시 임베딩
- **캐싱**: LRU 캐시 1000개 항목으로 중복 쿼리 최적화

#### 지능형 응답
- **RAG 파이프라인**: Retrieval → Context → Generation
- **컨텍스트 주입**: 검색된 문서 청크를 프롬프트에 포함
- **출처 표시**: 답변의 근거가 된 문서 파일명 표시
- **답변 캐싱**: 95% 유사도 기준 자동 캐시 응답
- **토큰 카운트**: 실시간 입력/출력 토큰 수 표시

#### 질문 생성
- **자동 질문 생성**: 문서당 12개 한국어 질문 자동 생성
- **백그라운드 처리**: 서버 시작 시 비동기 생성 (선택적)
- **다양한 질문 유형**: 사실 확인, 설명, 비교, 추론 등
- **자동완성 통합**: 생성된 질문을 자동완성 후보로 활용

### 🎨 사용자 인터페이스

#### 모던 웹 UI
- **반응형 디자인**: 모바일, 태블릿, 데스크톱 모두 지원
- **다크 모드**: 라이트/다크 테마 + 자동/수동 전환
- **Markdown 렌더링**: 코드 블록, 테이블, 리스트 등 완벽 지원
- **구문 강조**: Highlight.js로 코드 자동 색상 표시
- **애니메이션**: 부드러운 전환 효과 및 로딩 인디케이터
- **모달 스택 관리**: ESC 키로 중첩 모달을 LIFO 방식으로 제어

#### 대화 기능
- **스트리밍 표시**: 타이핑 효과로 실시간 답변 생성 표시
- **메시지 복사**: 답변 내용 클립보드 복사
- **답변 재생성**: 만족스럽지 않은 답변 다시 생성
- **중단 기능**: 생성 중인 답변 즉시 중단
- **토큰 추적**: 입력/출력 토큰 수 실시간 표시

#### 질문 자동완성
- **즉시 응답**: 2글자 입력 시 O(1) 검색으로 <5ms 응답
- **인덱스 기반**: 단어 인덱스로 10배 성능 향상
- **점수 기반 순위**: 접두사 매칭 + 관련성 점수
- **키보드 탐색**: 화살표(↑/↓)로 항목 선택, Enter로 입력

#### 문서 관리
- **드래그 앤 드롭**: 파일 끌어다 놓기로 간편 업로드
- **다중 업로드**: 여러 파일 동시 업로드 가능
- **진행률 표시**: 업로드 진행 상황 실시간 표시
- **문서 삭제**: 개별 문서 삭제 및 인덱스 자동 업데이트
- **문서 목록**: 업로드된 모든 문서 확인 및 관리
- **중복 방지**: MD5 해시로 동일 파일 재업로드 차단

#### 세션 관리
- **자동 저장**: 대화 내용 Redis에 자동 저장
- **세션 복원**: 페이지 새로고침 시 이전 대화 복원
- **대화 히스토리**: 좌측 사이드바에서 이전 대화 목록 확인
- **대화 전환**: 클릭으로 이전 대화 즉시 불러오기
- **전체 삭제**: 모든 대화 일괄 삭제 + 자동 새 대화 시작 (이중 확인)
- **타이틀 자동 생성**: 첫 질문 기반 대화 제목 자동 생성

#### 참고문서 상세
- **출처 표시**: 답변에 사용된 문서 파일명 표시
- **클릭으로 상세**: 파일명 클릭 시 원문 내용 모달 표시
- **하이브리드 로딩**: 캐시 우선 + 서버 폴백 전략
- **로딩 인디케이터**: 서버에서 데이터 가져올 때 상태 표시
- **유사도 점수**: 검색 결과 관련성 점수 표시

### 🚀 프로덕션 기능

#### 멀티 워커 서버
- **자동 스케일링**: CPU 코어 기반 워커 수 자동 설정 `(코어 * 2) + 1`
- **워커 범위**: 최소 4개, 최대 8개 워커
- **비동기 처리**: asyncio.to_thread()로 블로킹 작업 처리
- **워커 재활용**: 10,000 요청마다 자동 재시작 (메모리 누수 방지)
- **동시 요청**: 이벤트 루프 차단 없이 병렬 처리

#### 모니터링 및 관찰성
- **Health Check**: `/health` 엔드포인트로 시스템 상태 확인
  - Redis 연결 상태
  - 모델 로드 상태
  - CPU, 메모리, 디스크 사용률
  - 응답 시간: ~5ms (96% 최적화)
- **Prometheus 메트릭**: `/metrics` 엔드포인트
  - 캐시 히트율
  - Redis 연결 수
  - 시스템 리소스
  - 요청 카운트 및 지연 시간
- **Swagger UI**: `/docs` 인터랙티브 API 문서
- **ReDoc**: `/redoc` 읽기 전용 API 문서

#### 로깅 시스템
- **구조화된 로깅**: 타임스탬프, 레벨, 소스 위치 포함
- **로그 로테이션**: 100MB마다 회전, 7일 보관, 자동 압축
- **환경별 설정**: Production (INFO), Development (DEBUG)
- **파일 로깅**: 설정 가능한 로그 파일 경로
- **에러 추적**: 상세한 스택 트레이스 및 컨텍스트

#### 성능 최적화
- **연결 풀링**: Redis 50개 연결 풀
- **답변 캐싱**: 유사 질문 자동 감지 및 캐시 응답
- **Embedding 캐싱**: LRU 1000개 항목으로 GPU 추론 최적화
- **Java 캐싱**: Caffeine 500개 항목, 2시간 TTL
- **HTTP 압축**: JSON 응답 30-50% 크기 감소

#### 보안
- **CSP 헤더**: XSS 공격 차단, 허용 목록 방식
- **보안 헤더**: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection
- **서버 정보 숨김**: 버전 정보 노출 차단
- **CORS 설정**: 안전한 교차 출처 요청 정책
- **파일 검증**: Magic bytes 확인으로 위조 파일 차단

---

## 🏗️ 시스템 아키텍처

### 전체 구조도

```
┌────────────────────────────────────────────────────────────────┐
│                         웹 브라우저                              │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐  │
│  │  채팅 UI  │ │ 문서관리 │ │ 그룹관리 │ │   세션 관리       │  │
│  └─────┬────┘ └────┬─────┘ └────┬─────┘ └────────┬─────────┘  │
└────────┼───────────┼────────────┼─────────────────┼────────────┘
         │           │            │                 │
         ▼           ▼            ▼                 ▼
    HTTP/WebSocket API (FastAPI)
┌────────────────────────────────────────────────────────────────┐
│                     FastAPI 서버 (Python)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────┐    │
│  │  웹 서버      │  │ API 엔드포인트│  │  WebSocket 핸들러 │    │
│  │ (Uvicorn)    │  │ (REST API)   │  │  (스트리밍)        │    │
│  └──────┬───────┘  └──────┬───────┘  └─────────┬─────────┘    │
│         │                 │                    │              │
│  ┌──────▼─────────────────▼────────────────────▼──────────┐   │
│  │              비즈니스 로직 레이어                        │   │
│  │  ┌────────────┐ ┌───────────┐ ┌──────────────────┐    │   │
│  │  │ RAG 파이프라인│ │ 캐시 관리  │ │  그룹 관리        │    │   │
│  │  └──────┬─────┘ └─────┬─────┘ └────────┬─────────┘    │   │
│  └─────────┼─────────────┼────────────────┼──────────────┘   │
│            │             │                │                  │
│  ┌─────────▼─────┐ ┌─────▼─────┐  ┌───────▼────────┐        │
│  │  문서 처리     │ │ 벡터 DB    │  │  세션 관리      │        │
│  │ (Processor)   │ │ (Vector)   │  │ (Conversation)  │        │
│  └──────┬────────┘ └─────┬─────┘  └────────┬────────┘        │
└─────────┼────────────────┼─────────────────┼─────────────────┘
          │                │                 │
          │                ▼                 │
          │         ┌─────────────┐          │
          │         │   Redis     │◄─────────┘
          │         │ Vector DB   │
          │         │  + Cache    │
          │         └─────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│    Java Document Service (Spring Boot)   │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ PDF 추출     │  │ Office 문서 추출  │  │
│  │ (PDFBox)    │  │ (Apache POI)     │  │
│  └─────────────┘  └──────────────────┘  │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ HWP 추출     │  │ Caffeine Cache   │  │
│  │ (hwplib)    │  │ (500 items/2hr)  │  │
│  └─────────────┘  └──────────────────┘  │
└──────────────────────────────────────────┘
          │
          ▼
┌──────────────────────────────────────────┐
│          AI/ML 레이어                     │
│  ┌─────────────┐  ┌──────────────────┐  │
│  │ Qwen LLM    │  │ KURE-v1 Embed.  │  │
│  │ (MLX/CUDA)  │  │ (MPS/CUDA/CPU)   │  │
│  │ 3B/30B 4bit │  │ 1024-dim         │  │
│  └─────────────┘  └──────────────────┘  │
│         Apple Silicon GPU 가속           │
└──────────────────────────────────────────┘
```

### 데이터 흐름

#### 1. 문서 업로드 및 색인
```
[사용자] → [웹 UI] → [FastAPI]
                        ↓
            [Java Document Service]
                        ↓
              [텍스트 추출 완료]
                        ↓
              [LangChain 청킹]
                        ↓
            [KURE-v1 Embeddings 생성]
                        ↓
          [Redis Vector DB 저장]
```

#### 2. 질의응답 파이프라인
```
[사용자 질문] → [FastAPI]
                   ↓
         [KURE-v1 Embeddings 생성]
                   ↓
        [Redis Vector 검색]
                   ↓
       [Top-K 문서 청크 검색]
                   ↓
      [캐시 확인 (95% 유사도)]
         ↓ (miss)        ↓ (hit)
    [Qwen LLM]      [캐시 응답]
         ↓                ↓
   [답변 생성]       [즉시 응답]
         ↓                ↓
   [캐시 저장] ─────────────┘
         ↓
 [WebSocket 스트리밍]
         ↓
     [웹 UI 표시]
```

### 컴포넌트 상세

#### FastAPI 서버
- **역할**: HTTP/WebSocket API 서버, 비즈니스 로직 조정
- **포트**: 8000 (기본)
- **워커**: 4-8개 (자동)
- **비동기**: asyncio 기반

#### Redis
- **역할**: Vector DB, 캐시, 세션 저장소
- **포트**: 6379
- **모듈**: RediSearch, RedisJSON
- **연결 풀**: 50개

#### Java Document Service
- **역할**: 문서 텍스트 추출 (PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX)
- **포트**: 8080
- **프레임워크**: Spring Boot 3.5
- **JVM**: Java 21 + G1GC
- **Python 직접 처리**: TXT (UTF-8, CP949 인코딩)

#### AI 모델
- **LLM**: Qwen3 30B (4-bit 양자화)
- **Embeddings**: KURE-v1 (1024-dim, 한국어 특화)
- **가속**: Apple Metal (MPS), NVIDIA CUDA, CPU 자동 선택

---

## 🛠️ 기술 스택

### Backend (Python 3.10+)

| 카테고리 | 기술 | 용도 | 버전 |
|---------|------|------|------|
| **웹 프레임워크** | FastAPI | REST API, WebSocket | 0.115+ |
| | Uvicorn | ASGI 서버 | 0.38+ |
| | Pydantic | 데이터 검증 | 2.0+ |
| **AI/ML** | MLX | Apple GPU 가속 | latest |
| | Sentence Transformers | Embeddings | 3.0+ |
| | transformers | 모델 로딩 | 4.45+ |
| | torch | PyTorch | 2.5+ |
| **Vector DB** | redis | Redis 클라이언트 | 5.0+ |
| | redis-py | Python 바인딩 | latest |
| **문서 처리** | LangChain | 텍스트 청킹 | 0.3+ |
| | requests | HTTP 클라이언트 | 2.32+ |
| **유틸리티** | python-dotenv | 환경 변수 | 1.0+ |
| | psutil | 시스템 모니터링 | 6.0+ |
| | prometheus-client | 메트릭 | 0.21+ |

### Backend (Java 21)

| 카테고리 | 기술 | 용도 | 버전 |
|---------|------|------|------|
| **프레임워크** | Spring Boot | REST API | 3.5.0 |
| | Spring Web | 웹 서비스 | 3.5.0 |
| | Spring Cache | 캐싱 | 3.5.0 |
| **문서 처리** | Apache PDFBox | PDF 추출 | 3.0.3 |
| | Apache POI | Office 문서 | 5.3.0 |
| | hwplib | HWP 파일 | latest |
| **캐싱** | Caffeine | LRU 캐시 | 3.1.8 |
| **모니터링** | Micrometer | 메트릭 | latest |
| | Prometheus | 메트릭 수집 | latest |

### Database & Storage

| 기술 | 용도 | 포트 | 특징 |
|------|------|------|------|
| **Redis Stack** | Vector DB, Cache, Session | 6379 | RediSearch, RedisJSON |
| **Docker** | 컨테이너화 | - | Redis, Java Service |

### Frontend

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| **핵심** | HTML5/CSS3/ES6+ | 웹 UI |
| **Markdown** | Marked.js | Markdown 렌더링 |
| **코드 강조** | Highlight.js | 구문 강조 |
| **스타일** | CSS Variables | 테마 시스템 |
| **통신** | Fetch API, WebSocket | 서버 통신 |

### DevOps & Tools

| 카테고리 | 기술 | 용도 |
|---------|------|------|
| **컨테이너** | Docker, Docker Compose | 배포 |
| **빌드** | Maven | Java 빌드 |
| **패키지** | pip, venv | Python 패키지 |
| **모니터링** | Prometheus, Grafana (선택) | 시스템 모니터링 |

---

## 📋 시스템 요구사항

### 기본 구성 (Qwen3 30B 모델)

| 항목 | 요구사항 |
|------|----------|
| **OS** | macOS 14+ (Sonoma) with Apple Silicon 또는 Linux with NVIDIA GPU |
| **CPU** | Apple M2 Pro/Max/Ultra 또는 8코어+ Intel/AMD |
| **메모리** | 32GB RAM 이상 (24GB 최소) |
| **저장공간** | 50GB SSD |
| **GPU** | Apple M2 Pro/Max/Ultra 또는 NVIDIA GPU 16GB+ VRAM |

### 필수 소프트웨어

| 소프트웨어 | 용도 |
|----------|------|
| **Docker** | Redis, Document Service 컨테이너 실행 |
| **Redis Stack** | Vector DB (Docker로 설치 권장) |

### 소프트웨어 의존성

```bash
# 필수
- Python 3.10+
- Docker & Docker Compose
- Git

# 선택 (Java Document Service 사용 시)
- Java 21
- Maven 3.9+
```

### 포트 요구사항

| 포트 | 서비스 | 용도 |
|------|--------|------|
| 8000 | FastAPI | 웹 UI, API |
| 6379 | Redis | Vector DB, Cache |
| 8001 | RedisInsight | Redis 관리 (선택) |
| 8080 | Java Service | 문서 추출 (선택) |
| 8082 | Prometheus | 메트릭 (선택) |

---

## 🚀 빠른 시작

### 1단계: 저장소 클론

```bash
# 저장소 클론
git clone https://github.com/yourusername/chatbot_redis.git
cd chatbot_redis
```

### 2단계: 자동 설치 (권장)

```bash
# 설치 스크립트 실행
chmod +x setup.sh
./setup.sh
```

**설치 스크립트 기능**:
- ✅ 시스템 요구사항 자동 확인 (Python, Docker, Java)
- ✅ Python 가상환경 자동 생성 및 패키지 설치
- ✅ Redis 컨테이너 자동 시작
- ✅ 환경 설정 파일 (.env) 자동 생성
- ✅ 필수 디렉토리 구조 생성
- ✅ Java Document Service 설치 선택
- ✅ AI 모델 자동 다운로드 옵션

### 3단계: 문서 추가

```bash
# data 디렉토리에 문서 파일 복사
cp your_documents/*.pdf ./data/
cp your_documents/*.hwp ./data/
cp your_documents/*.{doc,docx,xls,xlsx,ppt,pptx,txt} ./data/
```

**지원 형식 (11가지)**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT

### 4단계: 서버 시작

```bash
# Foreground 실행 (개발용)
./run.sh

# Background 실행 (권장)
./run.sh --background  # 또는 -b
```

### 5단계: 웹 UI 접속

브라우저에서 http://localhost:8000 접속

**서비스 URL**:
- 💬 웹 UI: http://localhost:8000
- 📚 API 문서 (Swagger): http://localhost:8000/docs
- 📖 API 문서 (ReDoc): http://localhost:8000/redoc
- ❤️ Health Check: http://localhost:8000/health
- 📊 Metrics: http://localhost:8000/metrics
- 🔍 RedisInsight: http://localhost:8001 (선택)

### 수동 설치 (고급 사용자)

<details>
<summary>클릭하여 수동 설치 단계 보기</summary>

#### 1. Python 환경 설정

```bash
# 가상환경 생성
python3 -m venv venv

# 가상환경 활성화
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate  # Windows

# 패키지 설치
pip install --upgrade pip
pip install -r requirements.txt
```

#### 2. Redis 시작

```bash
# Docker Compose로 Redis 시작
docker-compose up -d redis

# Redis 상태 확인
docker-compose ps
```

#### 3. 환경 설정

```bash
# 환경 변수 파일 생성
cp .env.example .env

# .env 파일 편집 (필요시)
nano .env
```

#### 4. Java Document Service 빌드 (선택)

```bash
cd document-service
mvn clean package -DskipTests
cd ..

# Docker로 실행
docker-compose up -d document-service
```

#### 5. 서버 시작

```bash
# Python 서버 시작
python -m src.web_server
```

</details>

---

## 📖 사용 가이드

### 기본 사용법

#### 1. 첫 화면


- 환영 메시지와 추천 질문 표시
- 문서가 자동으로 로딩됨 (초기에는 시간 소요)
- 상태 표시줄에서 시스템 상태 확인

#### 2. 질문하기


**방법 1: 직접 입력**
```
입력 필드에 질문 입력 → Enter 또는 전송 버튼 클릭
```

**방법 2: 자동완성 사용**
```
2글자 이상 입력 → 자동완성 제안 표시
→ 화살표(↑/↓)로 선택 → Enter로 입력
```

**방법 3: 추천 질문 클릭**
```
환영 화면의 추천 질문 클릭 → 자동 입력 및 전송
```

#### 3. 답변 확인


- **스트리밍 표시**: 답변이 실시간으로 생성되어 표시
- **Markdown 렌더링**: 코드 블록, 테이블, 리스트 등 지원
- **참고 문서**: 답변 하단에 출처 파일명 표시
- **토큰 카운트**: 입력/출력 토큰 수 확인

#### 4. 답변 액션


- **복사**: 답변 내용을 클립보드에 복사
- **재생성**: 답변이 만족스럽지 않으면 다시 생성
- **중단**: 생성 중인 답변 즉시 중단

#### 5. 참고 문서 확인


```
참고 문서 파일명 클릭 → 모달 창에서 원문 내용 확인
```

- 문서의 실제 내용 표시
- 유사도 점수 확인
- 여러 청크가 있으면 모두 표시

### 문서 관리

#### 문서 업로드

**방법 1: 웹 UI 업로드**
```
1. 헤더의 "문서 관리" 버튼 클릭
2. "파일 선택" 또는 드래그 앤 드롭
3. 업로드 진행률 확인
4. 완료 후 자동 색인
```

**방법 2: 파일 시스템**
```bash
# data 디렉토리에 직접 복사
cp document.pdf ./data/

# 서버 재시작하면 자동 색인
./run.sh stop && ./run.sh --background
```

#### 문서 삭제

```
1. "문서 관리" 모달 열기
2. 삭제할 문서의 휴지통 아이콘 클릭
3. 확인 대화상자에서 "확인"
4. 인덱스에서 자동 제거
```

#### 문서 그룹 관리


**그룹 생성**:
```
1. "그룹 관리" 버튼 클릭
2. "그룹 추가" 클릭
3. 이름, 설명, 색상, 아이콘 입력
4. 부모 그룹 선택 (선택사항)
5. 저장
```

**문서 할당**:
```
1. 문서 관리 모달에서 문서 선택
2. 그룹 드롭다운에서 그룹 선택
3. 또는 그룹 관리에서 일괄 할당
```

**그룹별 검색**:
```
1. 필터 탭에서 "그룹별" 선택
2. 검색할 그룹 체크
3. OR 조건으로 검색 (여러 그룹 동시 선택 가능)
```

### 세션 관리

#### 대화 히스토리

**히스토리 보기**:
```
1. 좌측 사이드바 토글 버튼 클릭
2. 이전 대화 목록 확인
3. 클릭하여 대화 불러오기
```

**새 대화 시작**:
```
1. 사이드바의 "새 대화" 버튼 (+) 클릭
2. 또는 Ctrl+N (단축키)
```

**전체 삭제** (신규):
```
1. 사이드바의 "전체 삭제" 버튼 (휴지통) 클릭
2. 확인 다이얼로그에서 대화 개수 확인
3. "되돌릴 수 없습니다" 경고 확인
4. "확인" 클릭
5. 자동으로 새 대화 생성 및 환영 화면 표시
```

### 고급 기능

#### 필터링 검색

**문서별 필터**:
```
1. 필터 탭에서 "문서별" 선택
2. 특정 문서 체크
3. 선택한 문서에서만 검색
```

**그룹별 필터**:
```
1. 필터 탭에서 "그룹별" 선택
2. 특정 그룹 체크
3. 그룹에 속한 문서에서만 검색
```

#### 설정 조정


**검색 설정**:
- **Top-K**: 검색할 문서 청크 수 (1-10, 기본 5)

**생성 설정**:
- **Temperature**: 창의성 조절 (0-1, 기본 0.7)
- **Max Tokens**: 최대 응답 길이 (512-4096, 기본 2048)
- **LLM 모델**: 사용할 언어 모델 선택

**UI 설정**:
- **테마**: 라이트/다크/자동
- **폰트 크기**: 작게/보통/크게

#### 키보드 단축키

| 단축키 | 기능 |
|--------|------|
| `F1` | 도움말 모달 열기/닫기 |
| `Ctrl + N` | 새 대화 시작 |
| `Ctrl + /` | 대화 히스토리 사이드바 토글 |
| `Ctrl + K` | 입력 필드 포커스 |
| `Esc` | 최상위 모달 닫기 (LIFO 스택 방식) |
| `Enter` | 메시지 전송 |
| `Shift + Enter` | 줄바꿈 |

---

## 🔌 API 레퍼런스

### REST API

#### 인증
현재 버전에서는 인증이 필요하지 않습니다. 프로덕션 환경에서는 인증 추가를 권장합니다.

#### Base URL
```
http://localhost:8000
```

#### 엔드포인트 목록

### 1. Health Check

**시스템 상태 확인**

```http
GET /health
```

**응답 예시**:
```json
{
  "status": "healthy",
  "redis": {
    "connected": true,
    "ping": "PONG"
  },
  "models": {
    "embedding_loaded": true,
    "llm_loaded": true
  },
  "system": {
    "cpu_percent": 25.4,
    "memory_percent": 45.2,
    "disk_percent": 60.1
  },
  "timestamp": "2025-12-25T10:30:00Z"
}
```

### 2. 질의응답 (스트리밍)

**WebSocket 스트리밍 방식**

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');

ws.send(JSON.stringify({
  "question": "문서에서 주요 내용을 요약해주세요",
  "top_k": 5,
  "session_id": "session_123"
}));

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(data.token);  // 스트리밍 토큰
};
```

### 3. 질의응답 (일반)

**일반 HTTP POST 방식**

```http
POST /api/query
Content-Type: application/json

{
  "question": "문서에서 주요 내용을 요약해주세요",
  "top_k": 5,
  "session_id": "session_123",
  "filter_docs": ["document1.pdf", "document2.hwp"],
  "filter_groups": ["group-id-1", "group-id-2"]
}
```

**응답 예시**:
```json
{
  "answer": "문서의 주요 내용은 다음과 같습니다...",
  "sources": ["document1.pdf", "document2.hwp"],
  "context": [
    {
      "filename": "document1.pdf",
      "text": "문서 원문 내용...",
      "score": 0.95
    }
  ],
  "input_tokens": 50,
  "output_tokens": 150,
  "total_tokens": 200,
  "duration": 2.5
}
```

### 4. 문서 관리

#### 문서 목록 조회

```http
GET /api/documents
```

**응답**:
```json
{
  "documents": [
    {
      "filename": "document1.pdf",
      "size": 1024000,
      "uploaded_at": "2025-12-25T10:00:00Z",
      "chunks": 50,
      "group_id": "group-123"
    }
  ],
  "total": 10
}
```

#### 문서 업로드

```http
POST /api/documents/upload
Content-Type: multipart/form-data

file: <binary>
```

**응답**:
```json
{
  "filename": "document1.pdf",
  "status": "success",
  "chunks": 50,
  "message": "Document uploaded and indexed successfully"
}
```

#### 문서 삭제

```http
DELETE /api/documents/{filename}
```

**응답**:
```json
{
  "status": "success",
  "message": "Document deleted successfully",
  "filename": "document1.pdf"
}
```

#### 문서 청크 조회

```http
GET /api/documents/{filename}/chunks
```

**응답**:
```json
{
  "filename": "document1.pdf",
  "total_count": 50,
  "chunks": [
    {
      "index": 0,
      "text": "문서 내용...",
      "page": 1,
      "metadata": {}
    }
  ]
}
```

### 5. 그룹 관리

#### 그룹 목록 조회

```http
GET /api/groups
```

**응답**:
```json
{
  "groups": [
    {
      "id": "group-123",
      "name": "기술 문서",
      "description": "기술 관련 문서 모음",
      "color": "#4CAF50",
      "icon": "📚",
      "parent_id": null,
      "document_count": 15,
      "created_at": "2025-12-25T10:00:00Z"
    }
  ]
}
```

#### 그룹 생성

```http
POST /api/groups
Content-Type: application/json

{
  "name": "신규 그룹",
  "description": "설명",
  "color": "#4CAF50",
  "icon": "📁",
  "parent_id": "parent-group-id"
}
```

#### 그룹 수정

```http
PUT /api/groups/{group_id}
Content-Type: application/json

{
  "name": "수정된 이름",
  "description": "수정된 설명"
}
```

#### 그룹 삭제

```http
DELETE /api/groups/{group_id}
```

#### 문서를 그룹에 할당

```http
PUT /api/documents/{filename}/group
Content-Type: application/json

{
  "group_id": "group-123"
}
```

### 6. 세션 관리

#### 대화 목록 조회

```http
GET /api/conversations
```

**응답**:
```json
{
  "conversations": [
    {
      "session_id": "session-123",
      "title": "문서 요약에 대한 질문",
      "created_at": "2025-12-25T10:00:00Z",
      "updated_at": "2025-12-25T10:30:00Z",
      "message_count": 10
    }
  ]
}
```

#### 대화 내용 조회

```http
GET /api/conversations/{session_id}
```

**응답**:
```json
{
  "session_id": "session-123",
  "title": "문서 요약에 대한 질문",
  "messages": [
    {
      "role": "user",
      "content": "질문 내용",
      "timestamp": "2025-12-25T10:00:00Z"
    },
    {
      "role": "assistant",
      "content": "답변 내용",
      "metadata": {
        "sources": ["doc1.pdf"],
        "tokens": 150
      },
      "timestamp": "2025-12-25T10:00:05Z"
    }
  ]
}
```

#### 전체 대화 삭제 (신규)

```http
DELETE /api/conversations
```

**기능**:
- 모든 대화 기록 일괄 삭제
- 자동으로 새 대화 생성
- UI에서 이중 확인 다이얼로그 표시

**응답**:
```json
{
  "status": "success",
  "deleted_count": 25,
  "message": "Successfully deleted 25 conversations"
}
```

### 7. 시스템 관리

#### 문서 재색인

```http
POST /api/reindex
```

**응답**:
```json
{
  "status": "success",
  "indexed_files": 10,
  "total_chunks": 500,
  "duration": 30.5
}
```

#### 캐시 삭제

```http
POST /api/cache/clear
```

**응답**:
```json
{
  "status": "success",
  "cleared_entries": 150
}
```

#### Prometheus 메트릭

```http
GET /metrics
```

**응답**: Prometheus 형식의 메트릭

### API 에러 코드

| 코드 | 설명 |
|------|------|
| 200 | 성공 |
| 400 | 잘못된 요청 |
| 404 | 리소스를 찾을 수 없음 |
| 500 | 서버 내부 오류 |
| 503 | 서비스 이용 불가 (모델 로드 중) |

---

## 👨‍💻 개발자 가이드

### 프로젝트 구조

```
chatbot_redis/
├── data/                      # 📁 문서 저장 디렉토리
│   └── .document_metadata.json  # 문서 메타데이터 (자동 생성)
│
├── model/                     # 📁 AI 모델 저장 (자동 다운로드)
│   ├── mlx-community--Qwen3-30B-A3B-4bit/         # 프로덕션 LLM (기본)
│   ├── nlpai-lab--KURE-v1/                        # 임베딩 모델 (한국어 특화)
│   └── (선택) mlx-community--Qwen2.5-3B-Instruct-4bit/  # 경량 LLM
│
├── src/                       # 📁 Python 소스 코드
│   ├── __init__.py
│   ├── web_server.py          # FastAPI 서버 (메인)
│   ├── embeddings.py          # KURE-v1 Embeddings 모델
│   ├── llm.py                 # Qwen LLM 모델
│   ├── vector_db.py           # Redis Vector DB 관리
│   ├── cache_manager.py       # 답변 캐싱 시스템
│   ├── performance_optimizer.py # 백엔드 성능 최적화 (쿼리 캐싱, 모니터링)
│   ├── document_processor.py  # 통합 문서 처리
│   ├── document_tracker.py    # 문서 변경 감지
│   ├── document_service.py    # Java Service 클라이언트
│   ├── pdf_processor.py       # PDF 처리 (레거시)
│   ├── hwp_processor.py       # HWP 처리 (Fallback)
│   ├── group_manager.py       # 그룹 관리 로직
│   └── model_manager.py       # 모델 자동 다운로드
│
├── static/                    # 📁 프론트엔드 파일
│   ├── index.html             # 메인 HTML
│   ├── style.css              # 메인 스타일시트
│   ├── script.js              # 메인 JavaScript (현재 활성)
│   ├── utils.js               # 성능 유틸리티 (debounce, throttle, DOM 캐싱)
│   ├── optimizations.js       # 앱 최적화 (memoization, 가상 스크롤, 객체 풀링)
│   ├── error-handler.js       # 에러 처리 모듈
│   ├── error-styles.css       # 에러 스타일
│   ├── session-manager.js     # 세션 관리 모듈
│   ├── streaming-visualizer.js # 스트리밍 시각화
│   ├── streaming-styles.css   # 스트리밍 스타일
│   ├── follow-up-questions.js # 후속 질문 모듈
│   ├── follow-up-styles.css   # 후속 질문 스타일
│   ├── autocomplete.js        # 질문 자동완성
│   ├── autocomplete-styles.css # 자동완성 스타일
│   ├── group-manager.js       # 그룹 관리 UI
│   ├── group-styles.css       # 그룹 관리 스타일
│   └── js/                    # 📁 모듈화 구조 (준비 완료, 비활성)
│       ├── core/              # 핵심 유틸리티
│       │   ├── modal-manager.js  # 모달 스택 관리
│       │   └── utils.js          # 공통 유틸리티 함수
│       ├── features/          # 기능별 모듈
│       │   ├── chat.js           # 채팅 기능
│       │   ├── documents.js      # 문서 관리
│       │   ├── versions.js       # 버전 관리
│       │   ├── settings.js       # 설정 관리
│       │   ├── history.js        # 대화 기록
│       │   └── theme.js          # 테마 관리
│       ├── main.js            # 메인 엔트리 포인트
│       ├── README.md          # 모듈 사용 가이드
│       └── ARCHITECTURE.md    # 아키텍처 문서
│
├── document-service/               # 📁 Java Document Service
│   ├── src/main/java/com/chatbot/hwp/
│   │   ├── HwpServiceApplication.java
│   │   ├── controller/
│   │   │   ├── DocumentController.java
│   │   │   ├── PdfController.java
│   │   │   └── HwpController.java
│   │   ├── service/
│   │   │   ├── PdfExtractionService.java
│   │   │   ├── HwpExtractionService.java
│   │   │   └── OfficeExtractionService.java
│   │   ├── config/
│   │   │   └── CacheConfig.java
│   │   └── dto/
│   │       └── ExtractionResponse.java
│   ├── Dockerfile
│   └── pom.xml
│
├── claudedocs/                # 📁 프로젝트 문서
│   ├── ARCHITECTURE.md        # 아키텍처 문서
│   ├── OPTIMIZATION.md        # 최적화 가이드
│   ├── IMPROVEMENTS.md        # 개선 사항 문서
│   └── [기타 가이드]
│
├── scripts/                   # 📁 유틸리티 스크립트
│   └── migrate-modules.sh     # JavaScript 모듈 마이그레이션 검증 스크립트
│
├── .env.example               # 환경 변수 템플릿
├── .env                       # 환경 변수 (자동 생성, .gitignore)
├── .gitignore
├── docker-compose.yml         # Docker Compose 설정
├── requirements.txt           # Python 의존성
├── setup.sh                   # 설치 스크립트
├── run.sh                     # 실행 스크립트
├── stop.sh                    # 종료 스크립트
├── README.md                  # 이 파일
├── CHANGELOG.md               # 변경 이력
├── DEPLOYMENT_GUIDE.md        # 배포 가이드
├── MULTIPLATFORM_SUPPORT.md   # 멀티플랫폼 지원
└── LICENSE                    # 라이선스 파일
```

### 개발 환경 설정

#### 1. 저장소 포크 및 클론

```bash
# 저장소 포크
# GitHub에서 "Fork" 버튼 클릭

# 클론
git clone https://github.com/YOUR_USERNAME/chatbot_redis.git
cd chatbot_redis

# upstream 추가
git remote add upstream https://github.com/ORIGINAL_OWNER/chatbot_redis.git
```

#### 2. 개발 브랜치 생성

```bash
# develop 브랜치에서 시작
git checkout -b feature/your-feature-name develop
```

#### 3. 개발 환경 구성

```bash
# Python 가상환경
python3 -m venv venv
source venv/bin/activate

# 개발 의존성 설치
pip install -r requirements.txt
pip install -r requirements-dev.txt  # 개발 도구 (향후 추가)

# pre-commit 훅 설치 (향후)
# pre-commit install
```

#### 4. 로컬 서버 실행

```bash
# Redis 시작
docker-compose up -d redis

# 개발 모드로 서버 실행 (자동 재로드)
ENVIRONMENT=development python -m src.web_server --reload
```

### 코딩 컨벤션

#### Python

**PEP 8 준수**:
```python
# Good
def calculate_similarity_score(query: str, document: str) -> float:
    """Calculate cosine similarity between query and document.

    Args:
        query: User query string
        document: Document content string

    Returns:
        Similarity score between 0 and 1
    """
    pass

# Bad
def calc(q,d):
    pass
```

**타입 힌트 사용**:
```python
from typing import List, Dict, Optional

def process_documents(
    files: List[str],
    options: Optional[Dict[str, any]] = None
) -> List[Document]:
    pass
```

**Docstring 스타일**:
- Google 스타일 docstring 사용
- 모든 public 함수/클래스에 docstring 작성

#### JavaScript

**ES6+ 사용**:
```javascript
// Good
const fetchDocuments = async () => {
    const response = await fetch('/api/documents');
    return await response.json();
};

// Bad
function fetchDocuments() {
    return fetch('/api/documents')
        .then(response => response.json());
}
```

**명명 규칙**:
- camelCase: 변수, 함수
- PascalCase: 클래스
- UPPER_CASE: 상수

#### Java

**Google Java Style Guide 준수**:
```java
// Good
@Service
public class PdfExtractionService {
    private static final Logger logger = LoggerFactory.getLogger(PdfExtractionService.class);

    public String extractText(String filePath) throws IOException {
        // Implementation
    }
}

// Bad
@Service
public class pdfService {
    public String extract(String s) {
        // Implementation
    }
}
```

### 테스트 가이드

#### 단위 테스트 (향후 추가)

```python
# tests/test_embeddings.py
import pytest
from src.embeddings import EmbeddingModel

def test_embedding_generation():
    model = EmbeddingModel()
    text = "테스트 문장"
    embedding = model.encode(text)

    assert embedding is not None
    assert len(embedding) == 1024  # KURE-v1 dimension
    assert isinstance(embedding, np.ndarray)
```

#### 통합 테스트 (향후 추가)

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from src.web_server import app

client = TestClient(app)

def test_query_endpoint():
    response = client.post("/api/query", json={
        "question": "테스트 질문"
    })

    assert response.status_code == 200
    assert "answer" in response.json()
```

### 디버깅

#### Python 디버깅

```python
# 로깅 활성화
import logging
logging.basicConfig(level=logging.DEBUG)

# breakpoint 사용
def process_query(query: str):
    breakpoint()  # Python 3.7+
    # 또는 import pdb; pdb.set_trace()
    result = model.encode(query)
    return result
```

#### JavaScript 디버깅

```javascript
// 브라우저 개발자 도구 사용
console.log('[DEBUG] Query:', query);
debugger;  // 브레이크포인트

// 에러 추적
try {
    const result = await fetchData();
} catch (error) {
    console.error('[ERROR]', error);
    console.trace();
}
```

#### Redis 디버깅

```bash
# Redis CLI 접속
docker exec -it redis redis-cli

# 모든 키 확인
KEYS *

# 특정 키 조회
GET key_name

# Vector 검색 테스트
FT.SEARCH idx:documents "@filename:test.pdf"
```

### 성능 프로파일링

#### Python Profiling

```python
# cProfile 사용
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

# 프로파일링할 코드
process_documents()

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(10)
```

#### 메모리 프로파일링

```python
# memory_profiler 사용
from memory_profiler import profile

@profile
def load_large_model():
    model = Model.load()
    return model
```

### Git 워크플로우

#### 브랜치 전략

```
main (프로덕션)
  ├── develop (개발)
  │     ├── feature/new-feature
  │     ├── feature/another-feature
  │     └── bugfix/fix-issue
  └── hotfix/critical-bug
```

#### 커밋 메시지

```bash
# 형식
<type>(<scope>): <subject>

<body>

<footer>

# 예시
feat(api): Add document group filtering

- Add filter_groups parameter to query endpoint
- Implement OR condition for multiple groups
- Update API documentation

Closes #123
```

**Types**:
- `feat`: 새 기능
- `fix`: 버그 수정
- `docs`: 문서 변경
- `style`: 코드 포맷팅
- `refactor`: 리팩토링
- `perf`: 성능 개선
- `test`: 테스트 추가/수정
- `chore`: 빌드/설정 변경

### 릴리스 프로세스

1. **develop에서 기능 완료**
2. **버전 번호 업데이트** (CHANGELOG.md)
3. **release 브랜치 생성**
   ```bash
   git checkout -b release/v2.2.0 develop
   ```
4. **최종 테스트 및 버그 수정**
5. **main으로 머지**
   ```bash
   git checkout main
   git merge --no-ff release/v2.2.0
   git tag -a v2.2.0 -m "Release version 2.2.0"
   ```
6. **develop으로 백머지**
   ```bash
   git checkout develop
   git merge --no-ff release/v2.2.0
   ```
7. **푸시**
   ```bash
   git push origin main develop --tags
   ```

---

## ⚙️ 환경 설정

### 환경 변수 (`.env`)

```bash
# ===== 서버 설정 =====
HOST=0.0.0.0                    # 서버 호스트 (기본: 0.0.0.0)
PORT=8000                       # 서버 포트 (기본: 8000)
ENVIRONMENT=production          # production 또는 development

# ===== Redis 설정 =====
REDIS_HOST=localhost            # Redis 호스트
REDIS_PORT=6379                 # Redis 포트
REDIS_MAX_CONNECTIONS=50        # 연결 풀 크기 (프로덕션 최적화)
REDIS_SOCKET_TIMEOUT=5          # 소켓 타임아웃 (초)
REDIS_SOCKET_KEEPALIVE=true     # TCP keepalive 활성화
REDIS_SOCKET_KEEPALIVE_OPTIONS_IDLE=30  # Keepalive 간격

# ===== 캐시 설정 =====
CACHE_SIMILARITY_THRESHOLD=0.95 # 유사도 임계값 (0-1)
CACHE_TTL=3600                  # 캐시 TTL (초, 1시간)

# ===== AI 모델 설정 =====
EMBEDDING_MODEL=nlpai-lab/KURE-v1                   # KURE-v1 (1024-dim, 한국어 특화)
# LLM 모델 선택 (메모리 요구사항):
# - 프로덕션 기본: mlx-community/Qwen3-30B-A3B-4bit (~20GB RAM, 최고 성능)
# - 경량 옵션: mlx-community/Qwen2.5-3B-Instruct-4bit (~2GB RAM, 균형)
# - 초경량: mlx-community/Qwen2.5-1.5B-Instruct-4bit (~1.5GB RAM, 최소)
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit        # 프로덕션 기본값
MODEL_DIR=./model                                   # 모델 저장 경로

# ===== 문서 처리 설정 =====
DATA_DIR=./data                 # 문서 저장 경로
CHUNK_SIZE=512                  # 청크 크기 (토큰)
CHUNK_OVERLAP=50                # 청크 오버랩 (토큰)
MAX_FILE_SIZE_MB=100            # 최대 파일 크기 (MB)

# ===== Java Document Service =====
DOCUMENT_SERVICE_URL=http://localhost:8080  # Java 서비스 URL
HWP_SERVICE_URL=http://localhost:8080       # (레거시 호환)

# ===== 성능 최적화 =====
ENABLE_QUESTION_GENERATION=false  # 시작 시 질문 생성 (true/false)

# ===== Uvicorn 서버 설정 =====
TIMEOUT_KEEP_ALIVE=65           # Keep-alive 타임아웃 (초)
TIMEOUT_GRACEFUL_SHUTDOWN=30    # Graceful shutdown 대기 (초)
LIMIT_CONCURRENCY=1000          # 최대 동시 연결 수
LIMIT_MAX_REQUESTS=10000        # 워커당 최대 요청 수 (재시작 트리거)
BACKLOG=2048                    # 연결 대기 큐 크기

# ===== 로깅 설정 =====
LOG_LEVEL=info                  # debug, info, warning, error
LOG_FILE=/tmp/chatbot_production.log  # 로그 파일 경로
ACCESS_LOG=false                # 액세스 로그 활성화 (true/false)

# ===== 보안 설정 (향후) =====
# SECRET_KEY=your-secret-key    # JWT 서명 키
# ALLOWED_ORIGINS=http://localhost:3000,https://yourdomain.com
```

### Docker Compose 설정

```yaml
# docker-compose.yml
version: '3.8'

services:
  redis:
    image: redis/redis-stack:latest
    container_name: redis
    ports:
      - "6379:6379"      # Redis
      - "8001:8001"      # RedisInsight
    volumes:
      - redis_data:/data
    environment:
      - REDIS_ARGS=--maxmemory 2gb --maxmemory-policy allkeys-lru
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 30s
      timeout: 10s
      retries: 3

  document-service:
    build: ./document-service
    container_name: document-service
    ports:
      - "8080:8080"      # REST API
      - "8082:8082"      # Prometheus metrics
    environment:
      - SPRING_PROFILES_ACTIVE=production
      - SERVER_PORT=8080
      - MANAGEMENT_SERVER_PORT=8082
    volumes:
      - ./data:/app/data:ro
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/actuator/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  redis_data:
    driver: local
```

### Nginx 역방향 프록시 (선택)

```nginx
# /etc/nginx/sites-available/chatbot
server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket 타임아웃
        proxy_read_timeout 86400;
    }

    # Java Document Service
    location /api/extract {
        proxy_pass http://localhost:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 📊 성능 최적화

### 최신 최적화 현황 (2025-12-25)

#### Backend 최적화

**Health Endpoint**:
- ⚡ 응답 시간: 116ms → 4.9ms (96% 개선)
- CPU 모니터링: interval=0 (즉시 읽기)
- Redis 체크: INFO → PING (경량화)

**Embedding 캐싱**:
- 💾 LRU 캐시: 1000개 항목
- 🔑 캐시 키: MD5 해시
- ⚡ GPU 추론 스킵: 캐시 히트 시 즉시 응답

#### Frontend 최적화

**프로덕션 로그 제거**:
- 🧹 15+ console.log 문 제거
- ✅ DEBUG_MODE 보호 로그만 유지
- 📉 브라우저 성능 개선

**이벤트 위임**:
- 🎯 단일 이벤트 리스너
- 💾 메모리 효율 향상
- 🚀 동적 DOM 자동 처리

**하이브리드 로딩**:
- 📦 캐시 우선 전략
- 🔄 서버 폴백
- ⏱️ 로딩 인디케이터

#### Java API 최적화

**PDF 추출**:
- 📄 단일 패스 알고리즘
- ⚡ 다중 페이지 대폭 향상

**Caffeine 캐시**:
- 📦 500개 항목 (5배 증가)
- ⏰ 2시간 TTL (2배 증가)

**로깅**:
- 📝 INFO → DEBUG
- 📉 I/O 오버헤드 감소

### 성능 벤치마크

| 항목 | Before | After | 개선율 |
|------|--------|-------|--------|
| Health Check | 116ms | 4.9ms | 96% |
| 중복 쿼리 (캐시) | GPU 추론 | 즉시 응답 | ~99% |
| PDF 추출 (10페이지) | 2.5s | 0.8s | 68% |
| Java 캐시 적중률 | 80% | 90% | +10% |
| 프론트엔드 로그 노이즈 | 많음 | 최소 | ~90% |

### 추가 최적화 팁

#### 1. LLM 모델 선택

```bash
# 모델 크기별 메모리 요구사항:
# - Qwen3 30B: ~20GB RAM (기본 사용 중, 고성능)
# - Qwen 2.5 3B: ~2GB RAM (선택적 경량 옵션)
# - Qwen 2.5 1.5B: ~1.5GB RAM (선택적 초경량 옵션)

# 기본 설정 (현재 사용 중)
LLM_MODEL=mlx-community/Qwen3-30B-A3B-4bit

# 메모리 부족 시 경량 모델로 변경 가능 (별도 다운로드 필요)
# LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit
# LLM_MODEL=mlx-community/Qwen2.5-1.5B-Instruct-4bit
```

#### 2. 벡터 검색 튜닝

```python
# top_k 조정 (검색 문서 수)
top_k = 3  # 빠르지만 컨텍스트 부족 가능
top_k = 10  # 느리지만 컨텍스트 풍부
```

#### 3. 청크 크기 최적화

```bash
# 작은 청크: 정확하지만 느림
CHUNK_SIZE=256
CHUNK_OVERLAP=25

# 큰 청크: 빠르지만 정확도 낮을 수 있음
CHUNK_SIZE=1024
CHUNK_OVERLAP=100
```

#### 4. Redis 메모리 관리

```bash
# Redis 메모리 제한 및 정책
redis-cli CONFIG SET maxmemory 2gb
redis-cli CONFIG SET maxmemory-policy allkeys-lru
```

#### 5. 워커 수 조정

```bash
# 수동으로 워커 수 설정
uvicorn src.web_server:app --workers 8
```

---

## 🔧 문제 해결

### 일반적인 문제

#### 1. Redis 연결 오류

**증상**:
```
redis.exceptions.ConnectionError: Error connecting to Redis
```

**해결**:
```bash
# Redis 재시작
docker-compose restart redis

# Redis 로그 확인
docker-compose logs -f redis

# Redis 컨테이너 상태 확인
docker ps | grep redis

# Redis CLI 접속 테스트
docker exec -it redis redis-cli ping
```

#### 2. 모델 다운로드 실패

**증상**:
```
HfHubHTTPError: 401 Client Error: Unauthorized
```

**해결**:
```bash
# Hugging Face 토큰 설정
export HF_TOKEN=your_token_here

# 또는 .env에 추가
echo "HF_TOKEN=your_token_here" >> .env

# 수동 다운로드
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('nlpai-lab/KURE-v1')"
```

#### 3. Java Service 시작 실패

**증상**:
```
Failed to start document-service
```

**해결**:
```bash
# Java 버전 확인
java --version  # 17 이상 필요

# Maven 빌드
cd document-service
mvn clean package -DskipTests

# 로그 확인
docker-compose logs -f document-service

# 포트 충돌 확인
lsof -i :8080
```

#### 4. 파일 업로드 실패

**증상**:
```
413 Request Entity Too Large
```

**해결**:
```bash
# .env에서 제한 증가
MAX_FILE_SIZE_MB=200

# Nginx 사용 시 설정 추가
client_max_body_size 200M;
```

#### 5. 메모리 부족

**증상**:
```
MemoryError: Unable to allocate array
```

**해결**:
```bash
# 작은 모델 사용
# 경량 모델 사용 (별도 다운로드 필요)
# LLM_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit

# 배치 크기 감소 (코드 수정 필요)
# batch_size = 1

# 시스템 모니터링
htop
```

#### 6. 스트리밍 끊김

**증상**:
WebSocket 연결이 자주 끊어짐

**해결**:
```bash
# Nginx 타임아웃 증가
proxy_read_timeout 3600s;
proxy_send_timeout 3600s;

# 또는 .env에서
TIMEOUT_KEEP_ALIVE=3600
```

### 로그 확인

```bash
# Python 서버 로그
tail -f /tmp/chatbot_production.log

# Docker 로그
docker-compose logs -f

# Java 서비스 로그
docker-compose logs -f document-service

# Redis 로그
docker-compose logs -f redis
```

### 디버그 모드

```bash
# 개발 모드로 실행 (상세 로그)
ENVIRONMENT=development LOG_LEVEL=debug python -m src.web_server
```

---

## 🚢 배포 가이드

자세한 배포 가이드는 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)를 참조하세요.

### 간단한 배포 단계

#### 1. 프로덕션 환경 변수 설정

```bash
cp .env.example .env
nano .env

# 중요 설정 확인
ENVIRONMENT=production
LOG_LEVEL=info
TIMEOUT_KEEP_ALIVE=65
```

#### 2. Docker Compose 배포

```bash
# 빌드 및 시작
docker-compose up -d --build

# 상태 확인
docker-compose ps

# 로그 확인
docker-compose logs -f
```

#### 3. Systemd 서비스 (Linux)

```bash
# 서비스 파일 생성
sudo nano /etc/systemd/system/chatbot.service
```

```ini
[Unit]
Description=Document RAG Chatbot
After=network.target docker.service
Requires=docker.service

[Service]
Type=forking
User=your-user
WorkingDirectory=/path/to/chatbot_redis
ExecStart=/path/to/chatbot_redis/run.sh --background
ExecStop=/path/to/chatbot_redis/stop.sh
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

```bash
# 서비스 활성화
sudo systemctl daemon-reload
sudo systemctl enable chatbot
sudo systemctl start chatbot

# 상태 확인
sudo systemctl status chatbot
```

#### 4. Nginx 설정

```bash
# Nginx 설정 생성
sudo nano /etc/nginx/sites-available/chatbot

# 심볼릭 링크
sudo ln -s /etc/nginx/sites-available/chatbot /etc/nginx/sites-enabled/

# 설정 테스트
sudo nginx -t

# Nginx 재시작
sudo systemctl restart nginx
```

#### 5. SSL 인증서 (Let's Encrypt)

```bash
# Certbot 설치
sudo apt-get install certbot python3-certbot-nginx

# 인증서 발급
sudo certbot --nginx -d your-domain.com

# 자동 갱신 테스트
sudo certbot renew --dry-run
```

### 모니터링

#### Prometheus + Grafana

```yaml
# docker-compose.yml에 추가
services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
    restart: unless-stopped

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    volumes:
      - grafana_data:/var/lib/grafana
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    restart: unless-stopped
    depends_on:
      - prometheus
```

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'chatbot'
    static_configs:
      - targets: ['host.docker.internal:8000']

  - job_name: 'document-service'
    static_configs:
      - targets: ['document-service:8082']
```

---

## 🛡️ 보안

### 보안 체크리스트

- [ ] 환경 변수에 비밀 정보 저장 (`.env` 파일, `.gitignore`에 추가)
- [ ] HTTPS 사용 (프로덕션 환경)
- [ ] CORS 설정 (허용된 도메인만)
- [ ] 파일 업로드 검증 (Magic bytes, 크기 제한)
- [ ] 입력 검증 및 새니타이징
- [ ] 정기적인 의존성 업데이트
- [ ] 로그에 민감 정보 제외
- [ ] Redis 비밀번호 설정
- [ ] 방화벽 설정 (필요한 포트만 개방)
- [ ] 정기적인 보안 감사

### 보안 설정

#### Redis 비밀번호

```bash
# docker-compose.yml
services:
  redis:
    command: redis-server --requirepass your-password

# .env
REDIS_PASSWORD=your-password
```

#### CORS 설정

```python
# src/web_server.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://your-domain.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

#### 파일 업로드 검증

```python
# 이미 구현됨 (src/web_server.py)
ALLOWED_EXTENSIONS = {'.pdf', '.hwp', '.hwpx', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx'}
MAGIC_BYTES = {
    'pdf': b'%PDF',
    'hwp': b'\xd0\xcf\x11\xe0',
    # ...
}
```

### 취약점 대응

#### SQL/NoSQL 인젝션

- 현재 시스템은 Redis Vector DB 사용
- 사용자 입력은 임베딩으로 변환되어 인젝션 불가능

#### XSS (Cross-Site Scripting)

- CSP 헤더 설정됨
- Markdown 렌더링 시 sanitization 적용 (Marked.js)

#### CSRF (Cross-Site Request Forgery)

- SameSite Cookie 설정
- CSRF 토큰 (향후 추가 권장)

#### 파일 업로드 공격

- Magic bytes 검증
- 파일 크기 제한
- 안전한 파일명 처리

---

## 🤝 기여 가이드

### 기여 방법

1. **이슈 생성** 또는 **기존 이슈 선택**
2. **저장소 포크**
3. **브랜치 생성**: `git checkout -b feature/amazing-feature`
4. **변경 사항 커밋**: `git commit -m 'feat: Add amazing feature'`
5. **브랜치 푸시**: `git push origin feature/amazing-feature`
6. **Pull Request 생성**

### PR 체크리스트

- [ ] 코드가 프로젝트 코딩 컨벤션을 준수함
- [ ] Docstring/주석 추가 (필요 시)
- [ ] CHANGELOG.md 업데이트
- [ ] 테스트 추가/수정 (해당 시)
- [ ] 문서 업데이트 (해당 시)
- [ ] 모든 테스트 통과
- [ ] 의존성 추가 시 `requirements.txt` 업데이트

### 코드 리뷰 프로세스

1. **자동 체크**: CI/CD (향후 추가)
2. **리뷰어 지정**: 메인테이너가 리뷰
3. **피드백 반영**: 리뷰 코멘트 대응
4. **승인 후 머지**: 최소 1명 승인 필요

### 버그 리포트

이슈 생성 시 다음 정보 포함:

```markdown
### 버그 설명
간단한 버그 설명

### 재현 단계
1. '...' 로 이동
2. '...' 클릭
3. '...' 입력
4. 에러 발생

### 예상 동작
정상 동작 설명

### 실제 동작
실제로 일어난 일

### 환경
- OS: macOS 14.2
- Python: 3.11
- 브라우저: Chrome 120

### 스크린샷
(가능하면 스크린샷 첨부)
```

### 기능 제안

```markdown
### 기능 설명
제안하는 기능에 대한 설명

### 동기 및 배경
왜 이 기능이 필요한지

### 제안 구현 방법
(선택) 어떻게 구현할 수 있는지

### 대안
(선택) 고려한 다른 방법들
```

---

## ❓ FAQ

### Q1: Apple Silicon Mac이 아니면 사용할 수 없나요?

**A**: 아니요. Intel Mac, Linux, Windows (WSL2)에서도 사용 가능합니다. 다만 MLX는 Apple Silicon 전용이므로 CPU 모드로 실행됩니다. 성능은 떨어지지만 작동합니다.

### Q2: GPU가 없어도 실행 가능한가요?

**A**: 네. CPU만으로도 실행 가능하지만, 임베딩 생성과 LLM 추론이 느립니다. 작은 모델 사용을 권장합니다.

### Q3: 지원하는 문서 형식은?

**A**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT (총 10가지)
- **문서**: PDF, HWP, HWPX, DOC, DOCX
- **스프레드시트**: XLS, XLSX
- **프레젠테이션**: PPT, PPTX
- **텍스트**: TXT (UTF-8, CP949 인코딩 지원)

### Q4: 문서가 몇 개까지 처리 가능한가요?

**A**: Redis 메모리 제한 내에서 무제한입니다. 수천 개 문서도 처리 가능하지만, 메모리 사용량에 따라 조정 필요합니다.

### Q5: 질문 언어는 한국어만 지원하나요?

**A**: 한국어에 최적화되어 있지만, 영어 등 다국어도 지원합니다. LLM 모델이 다국어 모델이기 때문입니다.

### Q6: 인터넷 연결이 필요한가요?

**A**: 최초 모델 다운로드 시에만 필요합니다. 이후에는 오프라인에서도 작동합니다.

### Q7: 상업적으로 사용해도 되나요?

**A**: MIT 라이선스이므로 자유롭게 사용 가능합니다. 단, 사용하는 AI 모델의 라이선스도 확인하세요.

### Q8: 모델을 다른 것으로 변경할 수 있나요?

**A**: 네. `.env` 파일에서 `LLM_MODEL`과 `EMBEDDING_MODEL`을 변경하면 됩니다.

### Q9: 답변이 너무 느린데 어떻게 하나요?

**A**:
- 작은 모델 사용 (`Qwen2.5-1.5B-Instruct-4bit`)
- `top_k` 값 줄이기 (기본 5 → 3)
- `max_tokens` 값 줄이기 (기본 2048 → 1024)

### Q10: Redis 데이터를 백업하려면?

**A**:
```bash
# RDB 스냅샷 생성
docker exec redis redis-cli BGSAVE

# 백업 파일 복사
docker cp redis:/data/dump.rdb ./backup/

# 복원
docker cp ./backup/dump.rdb redis:/data/
docker-compose restart redis
```

---

## 📄 라이선스

이 프로젝트는 **MIT License**로 배포됩니다. 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

```
MIT License

Copyright (c) 2025 [Your Name]

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### 사용된 오픈소스

이 프로젝트는 다음 오픈소스 라이브러리를 사용합니다:

- [FastAPI](https://github.com/tiangolo/fastapi) - MIT License
- [Redis](https://github.com/redis/redis) - BSD 3-Clause License
- [MLX](https://github.com/ml-explore/mlx) - MIT License
- [Sentence Transformers](https://github.com/UKPLab/sentence-transformers) - Apache 2.0
- [Apache PDFBox](https://pdfbox.apache.org/) - Apache 2.0
- [Apache POI](https://poi.apache.org/) - Apache 2.0
- [Spring Boot](https://spring.io/projects/spring-boot) - Apache 2.0
- [Qwen](https://github.com/QwenLM/Qwen) - Tongyi Qianwen License

---

## 🙏 감사

이 프로젝트는 다음 기술과 커뮤니티의 도움으로 만들어졌습니다:

- **[nlpai-lab KURE](https://huggingface.co/nlpai-lab/KURE-v1)** - 한국어 특화 임베딩 모델
- **[Qwen Team](https://github.com/QwenLM/Qwen)** - 우수한 다국어 LLM
- **[MLX Team](https://github.com/ml-explore/mlx)** - Apple Silicon GPU 가속
- **[Redis Labs](https://redis.io/)** - 벡터 검색 기능
- **[FastAPI](https://fastapi.tiangolo.com/)** - 현대적인 웹 프레임워크
- **Apache Software Foundation** - PDFBox, POI 등 문서 처리 라이브러리
- **Open Source Community** - 모든 기여자와 사용자분들께 감사드립니다

---

## 📞 연락처 및 지원

- **이슈 트래커**: [GitHub Issues](https://github.com/yourusername/chatbot_redis/issues)
- **토론**: [GitHub Discussions](https://github.com/yourusername/chatbot_redis/discussions)
- **이메일**: your-email@example.com

---

## 🗺️ 로드맵

### ✅ 완료된 버전

#### v2.1.0 (2025-12-23) - 프로덕션 최적화 및 그룹 관리
- ✅ **문서 그룹 시스템**: 계층 구조, 드래그 앤 드롭, 그룹별 OR 검색
- ✅ **프로덕션 서버**: Multi-worker (CPU 기반 자동 스케일링), Health check, Prometheus 메트릭
- ✅ **Redis 최적화**: 연결 풀 50개, 소켓 keepalive, 헬스체크
- ✅ **API 문서**: Swagger UI, ReDoc 통합
- ✅ **캐시 개선**: 유사도 임계값, TTL 환경 변수 설정

#### v2.0.0 (2025-12-21) - 멀티 포맷 및 마이크로서비스
- ✅ **11가지 문서 형식**: PDF, HWP, HWPX, DOC, DOCX, XLS, XLSX, PPT, PPTX, TXT (신규)
- ✅ **Java Document Service**: Spring Boot 마이크로서비스, Apache POI + PDFBox
- ✅ **성능 최적화**: HTTP 연결 풀링, Caffeine 캐싱, 비동기 처리
- ✅ **모니터링**: Micrometer, Prometheus 엔드포인트

#### v1.0.0 (2024-12-XX) - 초기 릴리스
- ✅ PDF, HWP 문서 지원
- ✅ 한국어 RAG 챗봇
- ✅ Redis Vector DB
- ✅ KURE-v1 임베딩, Qwen LLM
- ✅ 웹 기반 채팅 인터페이스

---

### 📋 계획 중인 기능

#### v2.2.0 (다음 릴리스) - 엔터프라이즈 기능
**목표**: 다중 사용자 환경을 위한 보안 및 격리 기능

- [ ] **사용자 인증 시스템**
  - 이메일/비밀번호 회원가입 및 로그인
  - JWT 기반 토큰 인증 (Access: 1시간, Refresh: 7일)
  - 비밀번호 보안 정책 (bcrypt 해싱, 강도 검증)
  - 브루트포스 방지 (5회 실패 시 15분 잠금)
  - 세션 관리 및 자동 로그아웃

- [ ] **다중 사용자 격리**
  - 사용자별 독립적인 문서 저장소
  - 사용자별 대화 이력 격리
  - Redis Key 네임스페이스 분리 (`user:{user_id}:*`)
  - 벡터 검색 시 사용자 필터 자동 적용
  - 데이터 마이그레이션 스크립트 제공

- [ ] **API Key 관리**
  - API Key 생성/삭제 (`chatbot_` + 32자 랜덤)
  - 키별 권한 설정 (읽기 전용, 읽기/쓰기)
  - 키별 사용량 추적 및 통계
  - 키 만료일 설정 및 자동 무효화
  - Rate Limiting (키별 분당 요청 제한)

- [ ] **고급 필터링** (기본 필터는 v2.1.0에서 완료)
  - 날짜 범위 필터 (업로드 날짜, 문서 생성일)
  - 페이지 범위 필터 (특정 페이지만 검색)
  - 파일 크기 필터 (최소/최대 크기)
  - 복합 필터 조건 확장 (AND 연산 추가)

**문서**:
- 📋 [v2.2.0 설계 문서](claudedocs/V2.2.0_DESIGN.md)
- 🛠️ [v2.2.0 구현 가이드](claudedocs/V2.2.0_IMPLEMENTATION_GUIDE.md)

**예상 개발 기간**: 6주 (Phase 1~4)

#### v2.3.0 (향후 계획) - 고급 기능
- [ ] **웹훅 지원**: 이벤트 기반 알림
- [ ] **배치 처리 API**: 대량 문서 일괄 처리
- [ ] **문서 버전 관리**: 문서 버전 추적 및 롤백
- [ ] **감사 로그**: 사용자 활동 기록 및 추적

#### v3.0.0 (장기 로드맵) - 차세대 기능
- [ ] **다중 언어 UI**: 영어, 일본어, 중국어 등
- [ ] **음성 입력/출력**: STT/TTS 통합
- [ ] **이미지 OCR**: 이미지 내 텍스트 추출 및 검색
- [ ] **실시간 협업**: 다중 사용자 동시 작업

---

<div align="center">

**⭐ 이 프로젝트가 도움이 되었다면 Star를 눌러주세요! ⭐**

[맨 위로 이동](#-문서-rag-챗봇-document-rag-chatbot)

Made with ❤️ by [Your Name]

</div>
