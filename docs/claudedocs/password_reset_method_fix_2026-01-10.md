# 비밀번호 재설정 방식 변경 (2026-01-10)

## 문제 상황

로그인 페이지에서 "비밀번호를 잊으셨나요?" 링크 클릭 시 다음 오류 메시지가 표시되었습니다:

```
비밀번호 재설정은 관리자에게 문의하세요
```

사용자가 스스로 비밀번호를 재설정할 수 없는 상태였습니다.

## 원인 분석

### 설정 확인

```bash
$ curl http://localhost:8085/api/admin/password-reset-method

{
  "method": "admin",
  "email_configured": false,
  "message": "비밀번호 재설정 방식 조회 성공"
}
```

### 문제점

비밀번호 재설정 방식이 **"admin"**으로 설정되어 있었습니다:
- `method: "admin"` - 관리자에게 문의하는 방식
- 사용자가 직접 비밀번호를 재설정할 수 없음

### 코드 분석

**파일**: `static/login.html:347-349`

```javascript
} else if (method === 'admin') {
    // 관리자 방식: 안내 메시지 표시
    Auth.showError('비밀번호 재설정은 관리자에게 문의하세요');
}
```

## 해결 방법

### 1. 비밀번호 재설정 방식 변경

API를 사용하여 방식을 "email"로 변경:

```bash
curl -X PUT -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"email"}' \
  http://localhost:8085/api/admin/password-reset-method
```

**응답**:
```json
{
  "method": "email",
  "email_configured": false,
  "message": "비밀번호 재설정 방식이 이메일 방식(으)로 변경되었습니다"
}
```

### 2. 변경 확인

```bash
$ curl http://localhost:8085/api/admin/password-reset-method

{
  "method": "email",
  "email_configured": false,
  "message": "비밀번호 재설정 방식 조회 성공"
}
```

## 사용 가능한 방식

비밀번호 재설정 방식은 3가지가 있습니다:

### 1. Email 방식 (권장)
- **설정 값**: `"email"`
- **동작**: 이메일로 재설정 링크 전송
- **페이지**: `/static/reset-password.html`
- **요구사항**: SMTP 이메일 설정 필요

### 2. OTP 방식
- **설정 값**: `"otp"`
- **동작**: Google Authenticator로 본인 인증
- **페이지**: `/static/reset-password-otp.html`
- **요구사항**: 사용자가 미리 2FA 설정 필요

### 3. Admin 방식 (현재 설정)
- **설정 값**: `"admin"`
- **동작**: 관리자에게 문의하라는 메시지 표시
- **페이지**: 없음 (에러 메시지만 표시)
- **요구사항**: 없음

## 설정 변경 방법

### 방법 1: API 사용 (관리자 권한 필요)

```bash
# Email 방식으로 변경
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"email"}' \
  http://localhost:8085/api/admin/password-reset-method

# OTP 방식으로 변경
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"otp"}' \
  http://localhost:8085/api/admin/password-reset-method

# Admin 방식으로 변경 (비활성화)
curl -X PUT -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"method":"admin"}' \
  http://localhost:8085/api/admin/password-reset-method
```

### 방법 2: 관리자 페이지 사용

1. 관리자 페이지 로그인
2. **설정** 탭 선택
3. **비밀번호 재설정 방식** 섹션에서 원하는 방식 선택
4. 저장

## 이메일 설정 (Email 방식 사용 시)

비밀번호 재설정 방식을 "email"로 설정한 경우, SMTP 이메일 설정이 필요합니다.

### .env 파일 설정

```bash
# SMTP 설정
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=noreply@yourapp.com
SMTP_FROM_NAME=Your App Name

# 비밀번호 재설정 링크 유효 시간 (분)
PASSWORD_RESET_TOKEN_EXPIRE_MINUTES=30
```

### Gmail 앱 비밀번호 생성

1. Google 계정 보안 설정으로 이동
2. 2단계 인증 활성화
3. "앱 비밀번호" 생성
4. 생성된 비밀번호를 `SMTP_PASSWORD`에 설정

### 테스트

```bash
# 비밀번호 재설정 요청 테스트
curl -X POST -H "Content-Type: application/json" \
  -d '{"email":"user@example.com"}' \
  http://localhost:8085/api/auth/forgot-password
```

## 현재 상태

### ✅ 변경 완료
- 비밀번호 재설정 방식: **admin → email**
- 사용자가 로그인 페이지에서 "비밀번호를 잊으셨나요?" 클릭 시
- `/static/reset-password.html` 페이지로 이동 가능

### ⚠️ 주의사항
- **이메일 설정 필요**: `email_configured: false`
- 이메일 설정 없이는 재설정 이메일이 전송되지 않음
- SMTP 설정을 완료해야 실제로 비밀번호 재설정 가능

### 📋 다음 단계
1. ✅ 비밀번호 재설정 페이지 접근 가능 (완료)
2. ⏳ SMTP 이메일 설정 (선택 사항)
3. ⏳ 실제 이메일 전송 테스트

## 사용자 가이드

### 비밀번호 재설정 절차 (Email 방식)

1. **로그인 페이지 접속**
   - `http://localhost:8085/static/login.html`

2. **"비밀번호를 잊으셨나요?" 클릭**
   - 자동으로 `/static/reset-password.html`로 이동

3. **이메일 주소 입력**
   - 가입한 이메일 주소 입력
   - "재설정 링크 전송" 버튼 클릭

4. **이메일 확인**
   - 받은 이메일에서 재설정 링크 클릭

5. **새 비밀번호 설정**
   - 새 비밀번호 입력
   - 비밀번호 확인 입력
   - "비밀번호 변경" 버튼 클릭

## 관리자 설정 위치

관리자 페이지에서 비밀번호 재설정 방식을 언제든 변경할 수 있습니다:

**경로**: 관리자 페이지 → 설정 탭 → 비밀번호 재설정 방식

**옵션**:
- 📧 이메일 방식 (권장)
- 🔐 OTP 방식 (Google Authenticator)
- ⛔ 관리자 문의 (비활성화)

## 참고 파일

- **API 엔드포인트**: `src/routers/admin.py:868-927`
- **설정 관리**: `src/auth/password_reset_config.py`
- **로그인 페이지**: `static/login.html:324-354`
- **재설정 페이지**: `static/reset-password.html`
- **관리자 설정**: `static/admin.html:5653-5750`

---

**작성일**: 2026-01-10
**작성자**: Claude (Assistant)
**변경 사항**: 비밀번호 재설정 방식 admin → email 변경
