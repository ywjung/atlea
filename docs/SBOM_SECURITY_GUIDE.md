# SBOM 및 보안 취약점 관리 가이드

**버전**: 1.0.0
**최종 업데이트**: 2026-01-02

## 📋 목차

1. [개요](#개요)
2. [SBOM이란?](#sbom이란)
3. [시스템 구성](#시스템-구성)
4. [SBOM 생성](#sbom-생성)
5. [취약점 스캔](#취약점-스캔)
6. [의존성 업데이트](#의존성-업데이트)
7. [자동화 워크플로우](#자동화-워크플로우)
8. [보안 정책](#보안-정책)
9. [문제 해결](#문제-해결)
10. [참고 자료](#참고-자료)

---

## 개요

이 문서는 ATLEA 시스템의 **SBOM(Software Bill of Materials)** 생성 및 **보안 취약점 관리** 프로세스를 설명합니다.

### 목적

- 모든 소프트웨어 의존성 추적
- 보안 취약점 조기 발견 및 해결
- 라이선스 컴플라이언스 관리
- 공급망 보안 강화

### 적용 범위

- **Python 컴포넌트**: FastAPI 웹 애플리케이션, ML 라이브러리
- **Java 컴포넌트**: Spring Boot 문서 처리 서비스
- **전이적 의존성**: 모든 간접 의존성 포함

---

## SBOM이란?

### 정의

**SBOM(Software Bill of Materials)**은 소프트웨어 제품에 포함된 모든 구성 요소, 라이브러리, 모듈의 목록입니다.

### 중요성

- **투명성**: 제품에 무엇이 포함되어 있는지 명확히 파악
- **보안**: 취약점이 있는 컴포넌트 신속 식별
- **컴플라이언스**: 라이선스 의무사항 추적
- **공급망 보안**: Log4Shell 같은 공급망 공격 대응

### 표준 형식

우리 시스템은 다음 표준을 지원합니다:

- **CycloneDX**: 보안 중심의 SBOM 표준 (JSON, XML)
- **SPDX**: Linux Foundation의 표준 형식

---

## 시스템 구성

### Python 컴포넌트

**위치**: `/Users/jyw/works/ai/chatbot_redis/`

**주요 의존성**:
- FastAPI 0.115.0+
- Transformers 4.46.0+
- PyTorch 2.5.0+
- LangChain 0.3.10+
- Redis 5.2.0+

**보안 라이브러리**:
- python-jose (JWT)
- passlib (비밀번호 해싱)
- cryptography (암호화)

### Java 컴포넌트

**위치**: `/Users/jyw/works/ai/chatbot_redis/document-service/`

**주요 의존성**:
- Spring Boot 3.4.1
- Apache PDFBox 3.0.3
- Apache POI 5.3.0
- HWPLib 1.1.5

### 도구

| 도구 | 용도 | 언어 |
|------|------|------|
| pip-audit | 취약점 스캔 | Python |
| safety | 취약점 스캔 (대체) | Python |
| OWASP Dependency-Check | 취약점 스캔 | Java |
| CycloneDX Maven Plugin | SBOM 생성 | Java |
| CycloneDX Python | SBOM 생성 | Python |

---

## SBOM 생성

### 자동 생성

```bash
# 전체 SBOM 생성 (Python + Java)
./scripts/generate_sbom.sh
```

생성된 파일:
```
sbom/
├── python-sbom.json                 # pip-audit 결과
├── python-sbom-cyclonedx.json       # CycloneDX 형식
├── python-packages.json             # 설치된 패키지 목록
├── python-frozen-requirements.txt   # 고정 버전
├── java-sbom-cyclonedx.json         # Java CycloneDX SBOM
├── java-dependency-tree.txt         # Maven 의존성 트리
├── java-dependencies.txt            # 평면 의존성 목록
└── SBOM_SUMMARY.md                  # 요약 문서
```

### 수동 생성

#### Python SBOM

```bash
# pip-audit 사용
pip-audit --requirement requirements.txt --format cyclonedx-json --output sbom/python-sbom.json

# 패키지 목록
pip list --format=json > sbom/python-packages.json
pip freeze > sbom/python-frozen.txt
```

#### Java SBOM

```bash
cd document-service

# CycloneDX Maven 플러그인
mvn org.cyclonedx:cyclonedx-maven-plugin:2.8.2:makeAggregateBom

# 의존성 트리
mvn dependency:tree -DoutputFile=../sbom/java-deps.txt

# 의존성 목록
mvn dependency:list -DoutputFile=../sbom/java-list.txt
```

### SBOM 내용

생성된 SBOM에는 다음 정보가 포함됩니다:

- **컴포넌트 이름**: 패키지/라이브러리 이름
- **버전**: 정확한 버전 번호
- **라이선스**: 사용 라이선스 정보
- **저작자**: 제작자/관리자 정보
- **의존성 관계**: 직접/간접 의존성
- **해시값**: 무결성 검증용 체크섬
- **취약점 정보**: 알려진 CVE 목록

---

## 취약점 스캔

### 자동 스캔

```bash
# 전체 취약점 스캔 (Python + Java)
./scripts/scan_vulnerabilities.sh
```

스캔 결과:
```
sbom/scans/
├── python-vulnerabilities-YYYYMMDD_HHMMSS.json    # pip-audit 결과
├── python-vulnerabilities-YYYYMMDD_HHMMSS.txt     # 사람이 읽기 쉬운 형식
├── python-safety-YYYYMMDD_HHMMSS.json             # safety 결과
├── java-vulnerabilities-YYYYMMDD_HHMMSS.json      # OWASP 결과 (JSON)
├── java-vulnerabilities-YYYYMMDD_HHMMSS.html      # OWASP 결과 (HTML)
├── VULNERABILITY_REPORT_YYYYMMDD_HHMMSS.md        # 통합 보고서
└── VULNERABILITY_REPORT_LATEST.md                 # 최신 보고서 심볼릭 링크
```

### 수동 스캔

#### Python 취약점 스캔

```bash
# pip-audit (권장)
pip-audit --requirement requirements.txt

# JSON 출력
pip-audit --requirement requirements.txt --format json --output vulnerabilities.json

# safety (대체)
safety check --file requirements.txt
```

#### Java 취약점 스캔

```bash
cd document-service

# OWASP Dependency-Check
mvn org.owasp:dependency-check-maven:11.1.1:check

# HTML 리포트 생성
mvn org.owasp:dependency-check-maven:11.1.1:check -Dformat=HTML

# CVSS 7+ 점수만 실패 처리
mvn org.owasp:dependency-check-maven:11.1.1:check -DfailBuildOnCVSS=7
```

### 취약점 심각도 분류

| 심각도 | CVSS 점수 | 조치 기한 | 우선순위 |
|--------|-----------|-----------|----------|
| **Critical** | 9.0-10.0 | 즉시 (24시간) | 🔴 최우선 |
| **High** | 7.0-8.9 | 1주일 이내 | 🟠 높음 |
| **Medium** | 4.0-6.9 | 30일 이내 | 🟡 보통 |
| **Low** | 0.1-3.9 | 다음 릴리스 | 🔵 낮음 |
| **Info** | 0.0 | 모니터링 | 🟢 정보 |

### 알려진 취약점 예제

#### Python 취약점

```json
{
  "package": "cryptography",
  "version": "41.0.0",
  "vulnerability": "CVE-2023-50782",
  "severity": "HIGH",
  "cvss": 7.5,
  "description": "Bleichenbacher timing oracle attack",
  "fix": "Update to cryptography>=42.0.0"
}
```

#### Java 취약점

```json
{
  "name": "spring-webmvc",
  "version": "6.0.10",
  "vulnerability": "CVE-2023-34034",
  "severity": "CRITICAL",
  "cvssScore": 9.8,
  "description": "Path traversal vulnerability",
  "solution": "Upgrade to Spring Boot 3.1.2+"
}
```

---

## 의존성 업데이트

### 자동 업데이트

```bash
# 전체 의존성 업데이트
./scripts/update_dependencies.sh

# Python만 업데이트
./scripts/update_dependencies.sh --python-only

# Java만 업데이트
./scripts/update_dependencies.sh --java-only

# Dry run (변경사항 미리보기)
./scripts/update_dependencies.sh --dry-run
```

### 수동 업데이트

#### Python 패키지 업데이트

```bash
# 특정 패키지 업데이트
pip install --upgrade 'cryptography>=42.0.0'

# requirements.txt 재생성
pip freeze > requirements.txt

# 호환성 검증
pip check
```

#### Java 의존성 업데이트

```bash
cd document-service

# 특정 의존성 버전 변경 (pom.xml 직접 수정)
# 또는 Maven 플러그인 사용

# 최신 릴리스 버전으로 업데이트
mvn versions:use-latest-releases

# 부모 버전 업데이트
mvn versions:update-parent

# 사용 가능한 업데이트 확인
mvn versions:display-dependency-updates

# 변경사항 적용 후 검증
mvn clean verify
```

### 업데이트 프로세스

1. **백업 생성**: 자동으로 `backups/` 디렉토리에 백업
2. **취약점 확인**: 스캔 결과 검토
3. **우선순위 결정**: 심각도에 따라 업데이트 순서 결정
4. **의존성 업데이트**: 스크립트 실행 또는 수동 업데이트
5. **호환성 검증**: 컴파일 및 테스트 실행
6. **재스캔**: 취약점이 해결되었는지 확인
7. **SBOM 재생성**: 최신 의존성 목록 업데이트
8. **커밋**: 변경사항 버전 관리

### 업데이트 체크리스트

- [ ] 백업 확인
- [ ] 취약점 스캔 결과 검토
- [ ] 우선순위 높은 패키지 업데이트
- [ ] 의존성 충돌 해결
- [ ] 테스트 실행 및 통과 확인
- [ ] 재스캔으로 취약점 해결 확인
- [ ] SBOM 재생성
- [ ] 변경사항 문서화
- [ ] Git 커밋 및 푸시

---

## 자동화 워크플로우

### CI/CD 파이프라인 통합

#### GitHub Actions 예제

```yaml
name: Security Scan

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: '0 0 * * 0'  # 매주 일요일

jobs:
  sbom-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          java-version: '21'
          distribution: 'temurin'

      - name: Install dependencies
        run: |
          pip install pip-audit safety
          pip install -r requirements.txt

      - name: Generate SBOM
        run: ./scripts/generate_sbom.sh

      - name: Scan vulnerabilities
        run: ./scripts/scan_vulnerabilities.sh

      - name: Upload SBOM artifacts
        uses: actions/upload-artifact@v4
        with:
          name: sbom-reports
          path: sbom/

      - name: Upload scan results
        uses: actions/upload-artifact@v4
        with:
          name: vulnerability-scans
          path: sbom/scans/

      - name: Fail on critical vulnerabilities
        run: |
          # Critical 취약점이 있으면 빌드 실패
          if grep -q "CRITICAL" sbom/scans/VULNERABILITY_REPORT_LATEST.md; then
            echo "Critical vulnerabilities found!"
            exit 1
          fi
```

### 정기 스캔 스케줄

```bash
# crontab 설정
# 매주 월요일 오전 2시에 스캔 실행
0 2 * * 1 cd /path/to/chatbot_redis && ./scripts/scan_vulnerabilities.sh
```

### 알림 설정

```bash
# Slack 알림 예제 (scan_vulnerabilities.sh에 추가)
if [ $PYTHON_VULNS_FOUND -gt 0 ] || [ $JAVA_VULNS_FOUND -gt 0 ]; then
    curl -X POST -H 'Content-type: application/json' \
    --data '{"text":"⚠️ Security vulnerabilities detected in ATLEA!"}' \
    YOUR_SLACK_WEBHOOK_URL
fi
```

---

## 보안 정책

### 의존성 관리 정책

1. **최소 권한 원칙**: 필요한 패키지만 설치
2. **버전 고정**: 프로덕션에서는 정확한 버전 사용
3. **정기 업데이트**: 최소 월 1회 취약점 스캔
4. **즉시 패치**: Critical 취약점은 24시간 내 수정
5. **테스트 필수**: 모든 업데이트 후 테스트 실행

### 라이선스 컴플라이언스

허용된 라이선스:
- MIT
- Apache 2.0
- BSD (2-Clause, 3-Clause)
- Python Software Foundation License

제한적 라이선스 (법무팀 검토 필요):
- GPL, LGPL, AGPL
- Commercial licenses

금지된 라이선스:
- 독점 라이선스 (명시적 허가 없이)

### 보안 취약점 대응 프로세스

```
1. 취약점 발견
   ↓
2. 심각도 평가 (CVSS)
   ↓
3. 영향 범위 분석
   ↓
4. 패치 계획 수립
   ↓
5. 테스트 환경 업데이트
   ↓
6. 테스트 및 검증
   ↓
7. 프로덕션 배포
   ↓
8. 재스캔 및 확인
   ↓
9. 문서화
```

### 공급망 보안

- **신뢰할 수 있는 소스**: PyPI, Maven Central만 사용
- **무결성 검증**: 해시값 검증
- **서명 확인**: GPG 서명 확인 (가능한 경우)
- **미러 회피**: 공식 저장소 직접 사용
- **의존성 최소화**: 불필요한 패키지 제거

---

## 문제 해결

### 일반적인 문제

#### 1. pip-audit 설치 실패

```bash
# 해결: pip 업그레이드
pip install --upgrade pip
pip install pip-audit
```

#### 2. OWASP Dependency-Check 데이터 다운로드 실패

```bash
# 해결: 수동으로 NVD 데이터 다운로드
cd document-service
mkdir -p owasp-data
mvn org.owasp:dependency-check-maven:11.1.1:update-only -DdataDirectory=./owasp-data
```

#### 3. Maven SBOM 생성 실패

```bash
# 해결: 플러그인 캐시 삭제 후 재시도
rm -rf ~/.m2/repository/org/cyclonedx
mvn clean
mvn org.cyclonedx:cyclonedx-maven-plugin:2.8.2:makeAggregateBom
```

#### 4. False Positive 처리

Java의 경우 `owasp-suppressions.xml` 파일에 추가:

```xml
<suppress>
    <notes>
        이 취약점은 테스트 스코프에만 영향을 미치며 프로덕션 런타임에는 포함되지 않음
    </notes>
    <packageUrl regex="true">^pkg:maven/org\.example/vulnerable\-lib@.*$</packageUrl>
    <cve>CVE-2024-12345</cve>
</suppress>
```

Python의 경우 pip-audit에서 무시:

```bash
pip-audit --ignore-vuln CVE-2024-12345
```

### 성능 최적화

#### SBOM 생성 시간 단축

```bash
# Python: 캐시 사용
pip-audit --cache-dir ~/.cache/pip-audit

# Java: 병렬 빌드
mvn -T 4 org.cyclonedx:cyclonedx-maven-plugin:makeAggregateBom
```

#### 스캔 시간 단축

```bash
# OWASP: 증분 스캔 (변경된 부분만)
mvn org.owasp:dependency-check-maven:check -DcveValidForHours=24
```

---

## 참고 자료

### 공식 문서

- [CycloneDX 공식 사이트](https://cyclonedx.org/)
- [OWASP Dependency-Check](https://owasp.org/www-project-dependency-check/)
- [pip-audit Documentation](https://pypi.org/project/pip-audit/)
- [NIST NVD Database](https://nvd.nist.gov/)

### 도구

- [Snyk](https://snyk.io/) - 취약점 스캔 플랫폼
- [Grype](https://github.com/anchore/grype) - 컨테이너 이미지 스캔
- [Trivy](https://trivy.dev/) - 종합 보안 스캐너
- [Dependency-Track](https://dependencytrack.org/) - SBOM 관리 플랫폼

### 표준 및 규정

- [NIST SSDF](https://csrc.nist.gov/Projects/ssdf) - Secure Software Development Framework
- [SBOM Executive Order](https://www.whitehouse.gov/briefing-room/presidential-actions/2021/05/12/executive-order-on-improving-the-nations-cybersecurity/) - 미국 사이버보안 행정명령
- [OWASP Top 10](https://owasp.org/www-project-top-ten/) - 웹 애플리케이션 보안 위험

### 관련 CVE 데이터베이스

- [CVE Database](https://cve.mitre.org/)
- [GitHub Advisory Database](https://github.com/advisories)
- [Python Security Advisory](https://pypi.org/project/safety/)
- [Maven Central Security](https://central.sonatype.com/)

---

## 부록

### A. 스크립트 설명

| 스크립트 | 설명 | 실행 시간 |
|---------|------|-----------|
| `generate_sbom.sh` | Python과 Java SBOM 생성 | 2-5분 |
| `scan_vulnerabilities.sh` | 전체 취약점 스캔 | 5-15분 |
| `update_dependencies.sh` | 의존성 업데이트 및 재검증 | 10-30분 |

### B. 파일 구조

```
chatbot_redis/
├── scripts/
│   ├── generate_sbom.sh           # SBOM 생성
│   ├── scan_vulnerabilities.sh    # 취약점 스캔
│   └── update_dependencies.sh     # 의존성 업데이트
├── sbom/
│   ├── python-sbom-cyclonedx.json
│   ├── java-sbom-cyclonedx.json
│   ├── scans/
│   │   ├── python-vulnerabilities-latest.txt
│   │   ├── java-vulnerabilities-latest.html
│   │   └── VULNERABILITY_REPORT_LATEST.md
│   └── SBOM_SUMMARY.md
├── document-service/
│   ├── pom.xml                    # Maven 빌드 파일 (플러그인 추가됨)
│   └── owasp-suppressions.xml     # False positive 억제
├── requirements.txt               # Python 의존성
└── SBOM_SECURITY_GUIDE.md         # 이 문서
```

### C. 용어 사전

| 용어 | 설명 |
|------|------|
| **SBOM** | Software Bill of Materials - 소프트웨어 구성 요소 목록 |
| **CVE** | Common Vulnerabilities and Exposures - 공통 취약점 및 노출 |
| **CVSS** | Common Vulnerability Scoring System - 취약점 점수 체계 |
| **NVD** | National Vulnerability Database - 미국 국가 취약점 데이터베이스 |
| **CycloneDX** | SBOM 표준 형식 (OWASP 프로젝트) |
| **SPDX** | Software Package Data Exchange - 소프트웨어 패키지 데이터 교환 표준 |
| **OWASP** | Open Web Application Security Project - 오픈 웹 애플리케이션 보안 프로젝트 |
| **Transitive Dependency** | 전이적 의존성 - 간접적으로 포함되는 의존성 |

---

**최종 업데이트**: 2026-01-02
**버전**: 1.0.0
**관리자**: ATLEA Security Team
