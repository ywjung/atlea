"""
Query Rewriter - 쿼리 재작성 모듈

사용자의 자연어 질문을 검색에 최적화된 형태로 변환합니다.
LLM을 사용하여 쿼리를 확장하고, 관련 키워드와 동의어를 추가합니다.

📝 Changelog:
- 2026-01-22: 초기 구현
  - LLM 기반 쿼리 확장
  - 키워드 추출 및 동의어 생성
  - 원본 쿼리 보존
"""

import asyncio
from typing import Optional
from loguru import logger


class QueryRewriter:
    """
    LLM 기반 쿼리 재작성기

    사용자의 짧거나 모호한 질문을 검색에 최적화된 형태로 변환합니다.
    """

    # 쿼리 재작성 프롬프트 템플릿
    REWRITE_PROMPT_TEMPLATE = """당신은 검색 쿼리 최적화 전문가입니다.
사용자의 질문을 벡터 검색에 최적화된 형태로 확장해주세요.

## 규칙:
1. 원래 질문의 의도를 유지하세요
2. 관련 키워드, 동의어, 구체적 용어를 추가하세요
3. 불필요한 조사나 감탄사는 제거하세요
4. 검색에 도움이 되는 핵심 개념을 포함하세요
5. 너무 길지 않게 (최대 100자 이내) 작성하세요
6. 질문 형태가 아닌 키워드 나열 형태로 작성하세요

## GOOD 예시:
입력: "연차 이월돼?"
출력: "연차휴가 이월 가능 여부 미사용 연차 이월 한도 적용 기준"

입력: "급여 지급일이 언제야?"
출력: "급여 지급일 월급 지급 날짜 급여일 정기 급여"

입력: "휴가 신청 어떻게 해?"
출력: "휴가 신청 방법 절차 휴가 신청서 작성 승인 프로세스"

## BAD 예시 (이렇게 하지 마세요):
입력: "연차 이월돼?"
BAD: "연차 이월돼요?" (단순 어미 변환만 — 키워드 확장 없음)

입력: "급여 지급일이 언제야?"
BAD: "급여 지급일 언제" (동의어 부재, 확장 부족)

입력: "휴가 신청 어떻게 해?"
BAD: "휴가를 신청하는 방법에 대해 알려주세요" (질문 형태 유지 — 키워드 나열 필요)

## 변환할 질문:
{query}

## 검색 최적화 쿼리:"""

    def __init__(self, max_expanded_length: int = 150):
        """
        Query Rewriter 초기화

        Args:
            max_expanded_length: 확장된 쿼리의 최대 길이
        """
        self.max_expanded_length = max_expanded_length
        logger.info("✏️ QueryRewriter initialized")

    async def rewrite(
        self,
        query: str,
        llm_client,
        include_original: bool = True
    ) -> str:
        """
        쿼리 재작성

        Args:
            query: 원본 사용자 쿼리
            llm_client: LLM 클라이언트 (OllamaLLM 또는 호환 클라이언트)
            include_original: 원본 쿼리를 포함할지 여부

        Returns:
            확장된 검색 쿼리
        """
        if not query or len(query.strip()) == 0:
            return query

        # 이미 충분히 긴 쿼리는 재작성하지 않음
        if len(query) > 100:
            logger.debug(f"Query already long enough, skipping rewrite: {len(query)} chars")
            return query

        try:
            # 프롬프트 생성
            prompt = self.REWRITE_PROMPT_TEMPLATE.format(query=query)

            # LLM 호출 (비동기)
            if hasattr(llm_client, '_generate_response'):
                # OllamaLLM 인터페이스
                loop = asyncio.get_event_loop()
                expanded = await loop.run_in_executor(
                    None,
                    lambda: llm_client._generate_response(
                        messages=[{"role": "user", "content": prompt}],
                        max_tokens=100,
                        temperature=0.3
                    )
                )
            elif hasattr(llm_client, 'generate'):
                # 일반 generate 인터페이스
                expanded = await llm_client.generate(prompt, max_tokens=100)
            else:
                logger.warning("LLM client interface not recognized, skipping rewrite")
                return query

            # 결과 정리
            expanded = expanded.strip()

            # 길이 제한
            if len(expanded) > self.max_expanded_length:
                expanded = expanded[:self.max_expanded_length]

            # 원본 포함 옵션
            if include_original:
                # 원본이 이미 포함되어 있지 않으면 추가
                if query.lower() not in expanded.lower():
                    expanded = f"{query} {expanded}"

            logger.debug(f"✏️ Query rewritten: '{query}' → '{expanded}'")
            return expanded

        except Exception as e:
            logger.error(f"❌ Query rewrite failed: {e}")
            # 실패 시 원본 반환
            return query

    def extract_keywords(self, query: str) -> list:
        """
        쿼리에서 핵심 키워드 추출 (간단한 규칙 기반)

        Args:
            query: 사용자 쿼리

        Returns:
            키워드 리스트
        """
        # 불용어 목록 (한국어)
        stopwords = {
            '이', '그', '저', '것', '수', '등', '및', '를', '을', '에', '의',
            '가', '는', '은', '도', '로', '와', '과', '에서', '으로', '이다',
            '있다', '없다', '하다', '되다', '같다', '어떻게', '무엇', '언제',
            '어디', '왜', '누가', '뭐', '뭘', '좀', '해', '할', '하는', '어떤'
        }

        # 단어 분리 (공백 기준)
        words = query.split()

        # 불용어 제거 및 길이 필터링
        keywords = [
            word for word in words
            if len(word) > 1 and word not in stopwords
        ]

        return keywords

    def generate_synonyms(self, keyword: str) -> list:
        """
        키워드의 동의어 생성 (규칙 기반)

        Args:
            keyword: 키워드

        Returns:
            동의어 리스트
        """
        # 일반적인 비즈니스 동의어 매핑
        synonym_map = {
            # 휴가 관련
            '연차': ['연차휴가', '유급휴가', '연월차'],
            '휴가': ['휴무', '휴직', '쉬는날'],
            '병가': ['병가휴가', '병결'],

            # 급여 관련
            '급여': ['월급', '봉급', '임금', '페이'],
            '보너스': ['성과급', '인센티브', '상여금'],
            '연봉': ['년봉', '총급여', '연간급여'],

            # 근무 관련
            '출근': ['출퇴근', '근무시간'],
            '퇴근': ['퇴사시간', '업무종료'],
            '야근': ['초과근무', '시간외근무'],
            '재택': ['재택근무', '원격근무', '리모트'],

            # 복리후생
            '복지': ['복리후생', '베네핏', '혜택'],
            '보험': ['사회보험', '4대보험', '건강보험'],
            '교육': ['교육훈련', '연수', '트레이닝'],

            # 조직 관련
            '부서': ['팀', '조직', '부문'],
            '상사': ['팀장', '매니저', '관리자'],
            '회의': ['미팅', '회합', '협의']
        }

        return synonym_map.get(keyword, [])

    def expand_with_rules(self, query: str) -> str:
        """
        규칙 기반 쿼리 확장 (LLM 없이)

        Args:
            query: 원본 쿼리

        Returns:
            확장된 쿼리
        """
        keywords = self.extract_keywords(query)

        expanded_terms = list(keywords)
        for keyword in keywords:
            synonyms = self.generate_synonyms(keyword)
            expanded_terms.extend(synonyms[:2])  # 최대 2개 동의어 추가

        # 중복 제거
        expanded_terms = list(dict.fromkeys(expanded_terms))

        expanded_query = f"{query} {' '.join(expanded_terms)}"

        # 길이 제한
        if len(expanded_query) > self.max_expanded_length:
            expanded_query = expanded_query[:self.max_expanded_length]

        return expanded_query


class HybridQueryRewriter:
    """
    하이브리드 쿼리 재작성기

    LLM 기반과 규칙 기반을 결합하여
    안정적이고 효과적인 쿼리 확장을 수행합니다.
    """

    def __init__(
        self,
        use_llm: bool = True,
        fallback_to_rules: bool = True,
        max_expanded_length: int = 150
    ):
        """
        하이브리드 Query Rewriter 초기화

        Args:
            use_llm: LLM 사용 여부
            fallback_to_rules: LLM 실패 시 규칙 기반으로 폴백할지 여부
            max_expanded_length: 확장된 쿼리의 최대 길이
        """
        self.use_llm = use_llm
        self.fallback_to_rules = fallback_to_rules
        self.rewriter = QueryRewriter(max_expanded_length=max_expanded_length)
        logger.info(f"✏️ HybridQueryRewriter initialized (LLM: {use_llm}, fallback: {fallback_to_rules})")

    async def rewrite(
        self,
        query: str,
        llm_client=None,
        include_original: bool = True
    ) -> str:
        """
        하이브리드 쿼리 재작성

        Args:
            query: 원본 사용자 쿼리
            llm_client: LLM 클라이언트 (선택적)
            include_original: 원본 쿼리를 포함할지 여부

        Returns:
            확장된 검색 쿼리
        """
        if not query or len(query.strip()) == 0:
            return query

        # LLM 기반 확장 시도
        if self.use_llm and llm_client:
            try:
                expanded = await self.rewriter.rewrite(query, llm_client, include_original)

                # 유효한 확장인지 확인
                if expanded and len(expanded) > len(query):
                    return expanded

            except Exception as e:
                logger.warning(f"LLM-based rewrite failed: {e}")

        # 규칙 기반 폴백
        if self.fallback_to_rules:
            return self.rewriter.expand_with_rules(query)

        # 모두 실패 시 원본 반환
        return query
