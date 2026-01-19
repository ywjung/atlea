"""
Query Analyzer - 질문 분석 및 정보 소스 선택

📝 Changelog:
- 2025-01-19: 스마트 검색 모드 개선
  - INTERNAL_KEYWORDS 엄격화 (더 명시적인 내부 문서 지시어만)
  - WEB_BENEFICIAL_KEYWORDS 추가 (비교, 추천, 설명 등)
  - benefits_from_web 분석 필드 추가
  - 웹 검색이 도움되는 질문 유형 자동 감지
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

    # 내부 정보 키워드 (강한 내부 지시어 + 명시적 문서 참조)
    INTERNAL_KEYWORDS = [
        '우리 회사', '우리회사', '당사', '자사', '사내', '내부 문서', '내부문서',
        '우리 조직', '회사 정책', '회사정책', '내부 규정', '내부규정',
        'our company', 'our organization', 'internal policy', 'internal document'
    ]

    # 웹 검색이 도움되는 키워드 (외부 정보가 유용한 질문)
    WEB_BENEFICIAL_KEYWORDS = [
        # 비교/추천 질문
        '비교', '추천', '장단점', '차이점', '어떤 것이', '뭐가 좋',
        'vs', 'compare', 'recommend', 'pros cons', 'difference',
        # 일반 지식 질문
        '일반적으로', '보통', '평균', '표준', '기준', '트렌드',
        'generally', 'usually', 'standard', 'trend', 'average',
        # 사례/예시 질문
        '사례', '예시', '예제', '샘플', '모범', '벤치마크',
        'example', 'sample', 'case study', 'benchmark', 'best practice',
        # 방법/가이드 질문 (일반적인)
        '하는 방법', '하는 법', '어떻게 하', 'how to', 'how do',
        # 정보 탐색 질문
        '알려줘', '설명해', '무엇인가', '뭐야', '뭔가요', '어디서',
        'what is', 'explain', 'where can',
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
                'benefits_from_web': bool,
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
            'benefits_from_web': self._benefits_from_web(query_lower),
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

    def _benefits_from_web(self, query: str) -> bool:
        """
        웹 검색이 답변 품질을 향상시킬 수 있는지 판단

        Returns:
            True if web search would benefit the answer
        """
        # 웹 검색이 도움되는 키워드 확인
        if any(kw in query for kw in self.WEB_BENEFICIAL_KEYWORDS):
            return True

        # 질문 유형에 따른 판단
        query_type = self._classify_type(query)

        # 비교, 설명, 정의 질문은 웹 검색이 도움됨
        if query_type in ['comparison', 'explanation', 'definition']:
            return True

        # how-to 질문 중 일반적인 것 (내부 문서 키워드 없으면)
        if query_type == 'how-to' and not self._check_internal(query):
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
        # 웹 검색이 도움될 경우도 추가
        elif analysis.get('benefits_from_web', False):
            sources.append('web')

        # 기술 스택 명시 시 공식 문서 추가 (추후 Context7 통합)
        if analysis['tech_stack']:
            sources.append('docs')

        return sources
