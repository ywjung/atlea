"""
Personal Identifiable Information (PII) Detector
개인정보 검출 모듈 - 한국 개인정보 보호법 기준

지원 PII 타입:
- 주민등록번호
- 여권번호
- 운전면허번호
- 외국인등록번호
- 전화번호
- 이메일
- 신용카드번호
- 계좌번호
"""

import re
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class PIIType(Enum):
    """개인정보 타입"""
    RRN = "주민등록번호"  # Resident Registration Number
    PASSPORT = "여권번호"
    DRIVER_LICENSE = "운전면허번호"
    ALIEN_REG = "외국인등록번호"
    PHONE = "전화번호"
    EMAIL = "이메일"
    CREDIT_CARD = "신용카드번호"
    BANK_ACCOUNT = "계좌번호"
    ADDRESS = "주소"


@dataclass
class PIIMatch:
    """검출된 개인정보"""
    pii_type: PIIType
    value: str
    start: int
    end: int
    confidence: float  # 0.0 ~ 1.0


class PIIDetector:
    """개인정보 검출기"""

    def __init__(self):
        self._compile_patterns()

    def _compile_patterns(self):
        """정규식 패턴 컴파일"""
        self.patterns = {
            # 주민등록번호: 000000-0000000 (13자리)
            PIIType.RRN: re.compile(
                r'\b\d{6}[-\s]?\d{7}\b'
            ),

            # 여권번호: M12345678 (영문1자+숫자8자) 또는 S12345678
            PIIType.PASSPORT: re.compile(
                r'\b[A-Z]\d{8}\b'
            ),

            # 운전면허번호: 12-00-000000-00 (지역2-년도2-일련6-확인2)
            PIIType.DRIVER_LICENSE: re.compile(
                r'\b\d{2}[-\s]?\d{2}[-\s]?\d{6}[-\s]?\d{2}\b'
            ),

            # 외국인등록번호: 000000-0000000 (주민등록번호와 동일 형식, 뒷자리 첫자리가 5,6,7,8)
            PIIType.ALIEN_REG: re.compile(
                r'\b\d{6}[-\s]?[5-8]\d{6}\b'
            ),

            # 전화번호: 010-0000-0000, 02-000-0000 등
            PIIType.PHONE: re.compile(
                r'\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b'
            ),

            # 이메일: standard email pattern
            PIIType.EMAIL: re.compile(
                r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            ),

            # 신용카드번호: 0000-0000-0000-0000 (16자리)
            PIIType.CREDIT_CARD: re.compile(
                r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
            ),

            # 계좌번호: 은행별로 다양하지만 일반적으로 10-14자리
            PIIType.BANK_ACCOUNT: re.compile(
                r'\b\d{3,4}[-\s]?\d{2,6}[-\s]?\d{4,8}\b'
            ),

            # 주소: 도로명 + 번지 패턴 (간단한 패턴)
            PIIType.ADDRESS: re.compile(
                r'[가-힣]+[시|도|구|군|읍|면|동|로|길]\s*\d+[-\d]*'
            ),
        }

    def _validate_rrn(self, text: str) -> bool:
        """주민등록번호 유효성 검증 (체크섬 알고리즘)"""
        # 하이픈 제거
        rrn = text.replace('-', '').replace(' ', '')
        if len(rrn) != 13:
            return False

        try:
            # 체크섬 계산
            multipliers = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
            total = sum(int(rrn[i]) * multipliers[i] for i in range(12))
            check_digit = (11 - (total % 11)) % 10

            return int(rrn[12]) == check_digit
        except (ValueError, IndexError):
            return False

    def _validate_credit_card(self, text: str) -> bool:
        """신용카드번호 유효성 검증 (Luhn 알고리즘)"""
        # 하이픈과 공백 제거
        card = text.replace('-', '').replace(' ', '')
        if len(card) != 16:
            return False

        try:
            # Luhn 알고리즘
            total = 0
            for i, digit in enumerate(reversed(card)):
                n = int(digit)
                if i % 2 == 1:
                    n *= 2
                    if n > 9:
                        n -= 9
                total += n

            return total % 10 == 0
        except ValueError:
            return False

    def detect(self, text: str) -> List[PIIMatch]:
        """
        텍스트에서 개인정보 검출

        Args:
            text: 검사할 텍스트

        Returns:
            검출된 개인정보 목록
        """
        matches = []

        for pii_type, pattern in self.patterns.items():
            for match in pattern.finditer(text):
                value = match.group()
                confidence = 0.8  # 기본 신뢰도

                # 특정 타입에 대해 추가 검증
                if pii_type == PIIType.RRN:
                    if self._validate_rrn(value):
                        confidence = 0.95
                    else:
                        # 형식은 맞지만 체크섬이 틀린 경우 (false positive 가능성)
                        confidence = 0.6

                elif pii_type == PIIType.CREDIT_CARD:
                    if self._validate_credit_card(value):
                        confidence = 0.95
                    else:
                        confidence = 0.5

                # 전화번호와 계좌번호는 겹칠 수 있으므로 컨텍스트 기반 구분
                elif pii_type == PIIType.BANK_ACCOUNT:
                    # 전화번호 패턴과 겹치는 경우 제외
                    if re.match(r'\b0\d{1,2}[-\s]?\d{3,4}[-\s]?\d{4}\b', value):
                        continue

                matches.append(PIIMatch(
                    pii_type=pii_type,
                    value=value,
                    start=match.start(),
                    end=match.end(),
                    confidence=confidence
                ))

        # 중복 제거 (같은 위치의 여러 패턴 매칭)
        matches = self._remove_duplicates(matches)

        # 신뢰도 순으로 정렬
        matches.sort(key=lambda x: x.confidence, reverse=True)

        return matches

    def _remove_duplicates(self, matches: List[PIIMatch]) -> List[PIIMatch]:
        """중복된 매치 제거 (같은 위치, 더 높은 신뢰도 우선)"""
        if not matches:
            return matches

        # 위치별로 그룹화
        position_groups = {}
        for match in matches:
            key = (match.start, match.end)
            if key not in position_groups:
                position_groups[key] = []
            position_groups[key].append(match)

        # 각 위치에서 가장 높은 신뢰도만 선택
        result = []
        for group in position_groups.values():
            best_match = max(group, key=lambda x: x.confidence)
            result.append(best_match)

        return result

    def summarize(self, matches: List[PIIMatch]) -> Dict[str, int]:
        """
        검출 결과 요약

        Args:
            matches: 검출된 PII 목록

        Returns:
            PII 타입별 개수
        """
        summary = {}
        for match in matches:
            type_name = match.pii_type.value
            summary[type_name] = summary.get(type_name, 0) + 1

        return summary

    def mask_pii(self, text: str, matches: List[PIIMatch]) -> str:
        """
        개인정보 마스킹 (익명화)

        Args:
            text: 원본 텍스트
            matches: 마스킹할 PII 목록

        Returns:
            마스킹된 텍스트
        """
        # 뒤에서부터 마스킹 (인덱스 변경 방지)
        sorted_matches = sorted(matches, key=lambda x: x.start, reverse=True)

        masked_text = text
        for match in sorted_matches:
            mask = f"[{match.pii_type.value}]"
            masked_text = masked_text[:match.start] + mask + masked_text[match.end:]

        return masked_text


# 전역 인스턴스
_detector = None

def get_pii_detector() -> PIIDetector:
    """PII 검출기 싱글톤 인스턴스"""
    global _detector
    if _detector is None:
        _detector = PIIDetector()
    return _detector


# 편의 함수
def detect_pii(text: str) -> List[PIIMatch]:
    """텍스트에서 개인정보 검출"""
    detector = get_pii_detector()
    return detector.detect(text)


def has_pii(text: str, min_confidence: float = 0.6) -> bool:
    """개인정보 포함 여부 확인"""
    matches = detect_pii(text)
    return any(m.confidence >= min_confidence for m in matches)


def summarize_pii(text: str) -> Dict[str, int]:
    """개인정보 검출 요약"""
    detector = get_pii_detector()
    matches = detector.detect(text)
    return detector.summarize(matches)
