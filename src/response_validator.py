"""
Response Validator - AI 응답 품질 자동 검증
"""

import re
from typing import List, Tuple, Dict, Optional
from loguru import logger


class ResponseValidator:
    """AI 응답 품질 검증 및 자동 수정"""

    # 금지된 패턴들
    FORBIDDEN_PATTERNS = [
        (r'문서\s*\d+\s*을\s*기반으로', '문서 번호 기반 표현'),
        (r'문서\s*\d+\s*에\s*따르면', '문서 번호 따르면 표현'),
        (r'문서\s*\d+\s*는', '문서 번호 주어 표현'),
        (r'문서\s*\d+\s*가', '문서 번호 주어 표현'),
        (r'문서\s*\d+\s*의', '문서 번호 소유격 표현'),
        (r'\(문서\s*\d+\)', '괄호 안 문서 번호'),
        (r'\[문서\s*\d+\]', '대괄호 안 문서 번호'),
        (r'해당\s*문서(?!\s*\[)', '해당 문서 (파일명 없이)'),
        (r'제시된\s*문서(?!\s*\[)', '제시된 문서 (파일명 없이)'),
        (r'위\s*문서(?!\s*\[)', '위 문서 (파일명 없이)'),
        (r'Document\s*\d+', 'Document N 표현'),
        (r'Doc\s*\d+', 'Doc N 표현'),
    ]

    def __init__(self):
        """초기화"""
        self.violation_stats = {
            'total_checks': 0,
            'total_violations': 0,
            'violation_by_pattern': {}
        }

    def validate_response(self, response: str, context_filenames: List[str]) -> Tuple[bool, List[str]]:
        """
        응답 검증 및 위반 사항 반환

        Args:
            response: AI 응답 텍스트
            context_filenames: 컨텍스트에 사용된 파일명 리스트

        Returns:
            (is_valid, violations): 검증 통과 여부와 위반 사항 리스트
        """
        self.violation_stats['total_checks'] += 1
        violations = []

        # 1. 금지 패턴 검사
        for pattern, description in self.FORBIDDEN_PATTERNS:
            matches = re.findall(pattern, response, re.IGNORECASE)
            if matches:
                violation_msg = f"{description}: {matches}"
                violations.append(violation_msg)

                # 통계 업데이트
                if description not in self.violation_stats['violation_by_pattern']:
                    self.violation_stats['violation_by_pattern'][description] = 0
                self.violation_stats['violation_by_pattern'][description] += len(matches)

                logger.warning(f"🚨 응답 검증 실패 - {violation_msg}")

        # 2. 파일명 사용 여부 검사 (컨텍스트가 있는 경우에만)
        # 파일명 누락은 정보성 경고로만 기록 (자동 수정 기능이 있으므로)
        filename_warning = False
        if context_filenames:
            has_filename = any(
                filename.replace('[', '').replace(']', '') in response
                for filename in context_filenames
            )
            if not has_filename:
                filename_warning = True
                logger.info(f"ℹ️ 출처 정보: 응답에 파일명이 명시적으로 포함되지 않았으나 자동 수정이 적용됩니다")

        # 통계 업데이트 (금지 패턴 위반만 카운트)
        if violations:
            self.violation_stats['total_violations'] += 1

        # 금지 패턴 위반만 is_valid에 영향 (파일명 누락은 자동 수정되므로 제외)
        is_valid = len(violations) == 0

        if is_valid and not filename_warning:
            logger.debug("✅ 응답 검증 통과 - 모든 기준 충족")
        elif is_valid and filename_warning:
            logger.debug("✅ 응답 검증 통과 - 파일명은 자동 수정 예정")
        else:
            logger.error(f"❌ 응답 검증 실패 - {len(violations)}개 금지 패턴 발견")

        return is_valid, violations

    def auto_fix_response(self, response: str, context: List[Dict]) -> Tuple[str, List[str]]:
        """
        자동으로 "문서 N" → 실제 파일명으로 치환

        Args:
            response: AI 응답 텍스트
            context: 컨텍스트 문서 리스트 (filename 포함)

        Returns:
            (fixed_response, fixes_applied): 수정된 응답과 적용된 수정 사항 리스트
        """
        fixed_response = response
        fixes_applied = []

        # 각 문서에 대해 "문서 N" 패턴을 실제 파일명으로 치환
        for idx, doc in enumerate(context, 1):
            filename = doc.get('filename', '')
            if not filename:
                continue

            # 파일명을 대괄호로 감싸기
            filename_bracketed = f"[{filename}]"

            # 다양한 패턴 치환
            patterns_to_fix = [
                (rf'문서\s*{idx}\s*을\s*기반으로', f'{filename_bracketed}을 기반으로'),
                (rf'문서\s*{idx}\s*를\s*기반으로', f'{filename_bracketed}를 기반으로'),
                (rf'문서\s*{idx}\s*에\s*따르면', f'{filename_bracketed}에 따르면'),
                (rf'문서\s*{idx}\s*은', f'{filename_bracketed}은'),  # 주격 조사 (받침 O)
                (rf'문서\s*{idx}\s*는', f'{filename_bracketed}는'),  # 주격 조사 (받침 X)
                (rf'문서\s*{idx}\s*이', f'{filename_bracketed}이'),  # 주격 조사 (받침 O)
                (rf'문서\s*{idx}\s*가', f'{filename_bracketed}가'),  # 주격 조사 (받침 X)
                (rf'문서\s*{idx}\s*을', f'{filename_bracketed}을'),  # 목적격 조사 (받침 O)
                (rf'문서\s*{idx}\s*를', f'{filename_bracketed}를'),  # 목적격 조사 (받침 X)
                (rf'문서\s*{idx}\s*의', f'{filename_bracketed}의'),  # 관형격 조사
                (rf'\(문서\s*{idx}\)', f'({filename_bracketed})'),
                (rf'\[문서\s*{idx}\]', filename_bracketed),
                (rf'문서\s*{idx}(?=\s|,|\.|\)|\]|$)', filename_bracketed),
            ]

            for pattern, replacement in patterns_to_fix:
                old_response = fixed_response
                fixed_response = re.sub(pattern, replacement, fixed_response)

                if old_response != fixed_response:
                    fix_msg = f'"문서 {idx}" → "{filename}"'
                    fixes_applied.append(fix_msg)
                    logger.info(f"🔧 자동 수정 적용: {fix_msg}")

        # 일반적인 "해당 문서", "위 문서" 같은 표현도 처리
        if context:
            first_filename = f"[{context[0].get('filename', '')}]"

            vague_patterns = [
                (r'해당\s*문서(?!\s*\[)', f'{first_filename}'),
                (r'제시된\s*문서(?!\s*\[)', f'{first_filename}'),
                (r'위\s*문서(?!\s*\[)', f'{first_filename}'),
            ]

            for pattern, replacement in vague_patterns:
                old_response = fixed_response
                fixed_response = re.sub(pattern, replacement, fixed_response, count=1)

                if old_response != fixed_response:
                    fix_msg = f'모호한 표현 → "{context[0].get("filename", "")}"'
                    fixes_applied.append(fix_msg)
                    logger.info(f"🔧 자동 수정 적용: {fix_msg}")

        if fixes_applied:
            logger.success(f"✅ 자동 수정 완료 - {len(fixes_applied)}개 항목 수정")

        return fixed_response, fixes_applied

    def get_statistics(self) -> Dict:
        """검증 통계 반환"""
        pass_rate = 0.0
        if self.violation_stats['total_checks'] > 0:
            pass_rate = (
                (self.violation_stats['total_checks'] - self.violation_stats['total_violations'])
                / self.violation_stats['total_checks'] * 100
            )

        return {
            'total_checks': self.violation_stats['total_checks'],
            'total_violations': self.violation_stats['total_violations'],
            'pass_rate': f"{pass_rate:.1f}%",
            'violation_by_pattern': self.violation_stats['violation_by_pattern']
        }

    def reset_statistics(self):
        """통계 초기화"""
        self.violation_stats = {
            'total_checks': 0,
            'total_violations': 0,
            'violation_by_pattern': {}
        }
        logger.info("📊 검증 통계 초기화됨")


# 전역 인스턴스
response_validator = ResponseValidator()


# Export
__all__ = ['ResponseValidator', 'response_validator']
