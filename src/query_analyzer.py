"""
Query Analyzer - 질문 분석 및 정보 소스 선택

📝 Changelog:
- 2025-01-04: 하이브리드 RAG를 위한 질문 분석기 구현
  - 시간 민감도 판단
  - 내부/외부 정보 필요성 판단
  - 기술 스택 추출
"""

import re
from typing import Dict, List
from datetime import datetime
from loguru import logger


class QueryAnalyzer:
    """질문 의도 분석 및 정보 소스 선택"""

    # 시간 민감도 키워드
    TIME_SENSITIVE_KEYWORDS = {
        'high': [
            '최신', '현재', '요즘', '지금', '오늘', '이번주', '이번달',
            '2024', '2025', '2026',
            'latest', 'current', 'now', 'today', 'recent'
        ],
        'medium': [
            '최근', '새로운', '업데이트', '변경', '개선',
            'new', 'updated', 'changed', 'improved'
        ],
    }

    # 내부 정보 키워드
    INTERNAL_KEYWORDS = [
        '우리', '회사', '조직', '내부', '정책', '규정', '프로세스',
        '절차', '가이드', '매뉴얼', '업무', '부서',
        'our', 'company', 'internal', 'organization', 'policy'
    ]

    # 기술 스택 패턴 (버전 포함)
    TECH_PATTERNS = {
        'react': r'react\s*(\d+)?',
        'vue': r'vue\s*(\d+)?',
        'angular': r'angular\s*(\d+)?',
        'spring': r'spring\s*(boot)?\s*(\d+)?',
        'django': r'django\s*(\d+\.?\d*)?',
        'fastapi': r'fastapi\s*(\d+\.?\d*)?',
        'python': r'python\s*(\d+\.?\d*)?',
        'java': r'java\s*(\d+)?',
        'node': r'node\.?js\s*(\d+)?',
        'typescript': r'typescript\s*(\d+\.?\d*)?',
        'javascript': r'javascript|js\s*(\d+)?',
        'kotlin': r'kotlin\s*(\d+\.?\d*)?',
        'swift': r'swift\s*(\d+\.?\d*)?',
        'go': r'golang|go\s*(\d+\.?\d*)?',
        'rust': r'rust\s*(\d+\.?\d*)?',
        'php': r'php\s*(\d+\.?\d*)?',
        'ruby': r'ruby\s*(\d+\.?\d*)?',
        'docker': r'docker',
        'kubernetes': r'kubernetes|k8s',
        'aws': r'aws|amazon\s*web\s*services',
        'azure': r'azure',
        'gcp': r'gcp|google\s*cloud',
    }

    def analyze(self, query: str) -> Dict:
        """
        질문 분석하여 메타데이터 반환

        Args:
            query: 사용자 질문

        Returns:
            분석 결과 딕셔너리
            {
                'time_sensitivity': 'high' | 'medium' | 'low',
                'is_internal': bool,
                'tech_stack': List[Dict],
                'needs_fresh_info': bool,
                'query_type': str,
                'has_version': bool,
                'original_query': str
            }
        """
        query_lower = query.lower()

        analysis = {
            'time_sensitivity': self._check_time_sensitivity(query_lower),
            'is_internal': self._check_internal(query_lower),
            'tech_stack': self._extract_tech_stack(query),
            'needs_fresh_info': self._needs_fresh_info(query_lower),
            'query_type': self._classify_type(query_lower),
            'has_version': self._has_version_info(query),
            'original_query': query
        }

        logger.debug(f"Query analysis: {analysis}")
        return analysis

    def _check_time_sensitivity(self, query: str) -> str:
        """
        시간 민감도 체크

        Returns:
            'high' | 'medium' | 'low'
        """
        # High sensitivity keywords
        if any(kw in query for kw in self.TIME_SENSITIVE_KEYWORDS['high']):
            return 'high'

        # Medium sensitivity keywords
        if any(kw in query for kw in self.TIME_SENSITIVE_KEYWORDS['medium']):
            return 'medium'

        # Low sensitivity (default)
        return 'low'

    def _check_internal(self, query: str) -> bool:
        """
        내부 문서 관련 질문인지 체크

        Returns:
            True if internal document query
        """
        return any(kw in query for kw in self.INTERNAL_KEYWORDS)

    def _extract_tech_stack(self, query: str) -> List[Dict]:
        """
        기술 스택 및 버전 추출

        Returns:
            List of {'name': str, 'version': str|None}
        """
        tech_stack = []
        query_lower = query.lower()

        for tech, pattern in self.TECH_PATTERNS.items():
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                # Extract version if exists
                version = None
                if match.lastindex and match.lastindex > 0:
                    version = match.group(match.lastindex)

                tech_stack.append({
                    'name': tech,
                    'version': version
                })

        return tech_stack

    def _needs_fresh_info(self, query: str) -> bool:
        """
        최신 정보 필요 여부

        Returns:
            True if fresh information needed
        """
        current_year = datetime.now().year

        # 현재 년도 언급
        if str(current_year) in query or str(current_year - 1) in query:
            return True

        # 시간 민감 키워드 포함
        if self._check_time_sensitivity(query) != 'low':
            return True

        # 뉴스, 트렌드 관련 키워드
        news_keywords = ['뉴스', '소식', '발표', '릴리즈', '출시', 'news', 'release', 'announcement']
        if any(kw in query for kw in news_keywords):
            return True

        return False

    def _classify_type(self, query: str) -> str:
        """
        질문 유형 분류

        Returns:
            'how-to' | 'explanation' | 'definition' | 'comparison' | 'general'
        """
        # How-to questions
        if any(word in query for word in ['어떻게', 'how', '방법', '하는법', '하려면']):
            return 'how-to'

        # Explanation questions
        if any(word in query for word in ['왜', 'why', '이유', '원인', '때문']):
            return 'explanation'

        # Definition questions
        if any(word in query for word in ['무엇', 'what', '뭐', '정의', '의미']):
            return 'definition'

        # Comparison questions
        if any(word in query for word in ['비교', 'vs', '차이', '다른점', 'difference', 'compare']):
            return 'comparison'

        # General
        return 'general'

    def _has_version_info(self, query: str) -> bool:
        """
        버전 정보 포함 여부

        Returns:
            True if version information exists
        """
        # 버전 패턴: v1.0, 1.0, v1, 등
        version_pattern = r'v?\d+\.?\d*'
        return bool(re.search(version_pattern, query))

    def get_recommended_sources(self, analysis: Dict) -> List[str]:
        """
        분석 결과를 바탕으로 추천 정보 소스 반환

        Args:
            analysis: analyze() 결과

        Returns:
            ['local', 'web', 'docs'] 중 조합
        """
        sources = []

        # 내부 문서 질문이면 로컬만
        if analysis['is_internal']:
            return ['local']

        # 기본적으로 로컬 포함
        sources.append('local')

        # 최신 정보 필요 시 웹 검색 추가
        if analysis['needs_fresh_info']:
            sources.append('web')

        # 기술 스택 명시 시 공식 문서 추가 (추후 Context7 통합)
        if analysis['tech_stack']:
            sources.append('docs')

        return sources
