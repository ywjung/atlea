"""
Tests for ConfidenceScorer

📝 Changelog:
- 2025-12-30: Created comprehensive confidence scorer tests
  - Score calculation accuracy
  - Factor weighting
  - Level classification
  - Recommendation generation
"""

import pytest
from src.confidence_scorer import ConfidenceScorer


@pytest.fixture
def scorer():
    """ConfidenceScorer instance"""
    return ConfidenceScorer()


@pytest.fixture
def sample_context_high_relevance():
    """Sample context with high relevance scores"""
    return [
        {'filename': 'doc1.pdf', 'score': 0.95, 'content': 'High relevance content'},
        {'filename': 'doc2.pdf', 'score': 0.90, 'content': 'Also high relevance'},
        {'filename': 'doc3.pdf', 'score': 0.88, 'content': 'Good relevance'}
    ]


@pytest.fixture
def sample_context_low_relevance():
    """Sample context with low relevance scores"""
    return [
        {'filename': 'doc1.pdf', 'score': 0.55, 'content': 'Low relevance'}
    ]


class TestConfidenceScorer:
    """Tests for ConfidenceScorer initialization and weights"""

    def test_initialization(self, scorer):
        """Test scorer initialization"""
        assert scorer.score_weights['relevance'] == 0.40
        assert scorer.score_weights['coverage'] == 0.25
        assert scorer.score_weights['sources'] == 0.20
        assert scorer.score_weights['specificity'] == 0.15

    def test_weights_sum_to_one(self, scorer):
        """Test that weights sum to 1.0"""
        total = sum(scorer.score_weights.values())
        assert abs(total - 1.0) < 0.001  # Allow floating point precision


class TestRelevanceScore:
    """Tests for relevance score calculation"""

    def test_high_relevance_context(self, scorer, sample_context_high_relevance):
        """Test relevance score with high scores"""
        score = scorer._calculate_relevance_score(sample_context_high_relevance)
        assert score > 0.8
        assert score <= 1.0

    def test_low_relevance_context(self, scorer, sample_context_low_relevance):
        """Test relevance score with low scores"""
        score = scorer._calculate_relevance_score(sample_context_low_relevance)
        assert score < 0.5

    def test_empty_context(self, scorer):
        """Test relevance score with no context"""
        score = scorer._calculate_relevance_score([])
        assert score == 0.0

    def test_relevance_normalization(self, scorer):
        """Test relevance score normalization"""
        # Score 0.5 should map to 0.0 after normalization
        context = [{'score': 0.5}]
        score = scorer._calculate_relevance_score(context)
        assert score == 0.0

        # Score 1.0 should map to 1.0
        context = [{'score': 1.0}]
        score = scorer._calculate_relevance_score(context)
        assert score == 1.0


class TestCoverageScore:
    """Tests for coverage score calculation"""

    def test_optimal_length_answer(self, scorer):
        """Test coverage with optimal answer length"""
        answer = "A" * 500  # Optimal range 50-2000
        question = "What is this about?"
        score = scorer._calculate_coverage_score(answer, question)
        assert score > 0.3  # At least length component

    def test_very_short_answer(self, scorer):
        """Test coverage with very short answer"""
        answer = "Short"  # < 50 chars
        question = "What is this?"
        score = scorer._calculate_coverage_score(answer, question)
        assert score < 0.5

    def test_very_long_answer(self, scorer):
        """Test coverage with very long answer"""
        answer = "A" * 3000  # > 2000 chars
        question = "What is this?"
        score = scorer._calculate_coverage_score(answer, question)
        assert score < 1.0

    def test_structured_answer(self, scorer):
        """Test coverage with structured answer (markdown)"""
        answer = """
        # Header
        - Item 1
        - Item 2

        1. First
        2. Second
        """
        question = "Explain this"
        score = scorer._calculate_coverage_score(answer, question)
        assert score > 0.5  # Structure bonus

    def test_keyword_overlap(self, scorer):
        """Test coverage with question keyword overlap"""
        answer = "Python is a programming language used for development"
        question = "What is Python programming language?"
        score = scorer._calculate_coverage_score(answer, question)
        assert score > 0.5  # Good keyword overlap


class TestSourcesScore:
    """Tests for sources score calculation"""

    def test_no_sources(self, scorer):
        """Test sources score with no context"""
        score = scorer._calculate_sources_score([], "Some answer")
        assert score == 0.0

    def test_single_source(self, scorer):
        """Test sources score with one source"""
        context = [{'filename': 'doc.pdf'}]
        score = scorer._calculate_sources_score(context, "Answer")
        # Single source: count_score=0.5 * 0.6 + citation_score=0 * 0.4 = 0.3
        assert abs(score - 0.3) < 0.01

    def test_two_sources(self, scorer):
        """Test sources score with two sources"""
        context = [{'filename': 'doc1.pdf'}, {'filename': 'doc2.pdf'}]
        score = scorer._calculate_sources_score(context, "Answer")
        # Two sources: count_score=0.7 * 0.6 + citation_score=0 * 0.4 = 0.42
        assert abs(score - 0.42) < 0.01

    def test_three_or_more_sources(self, scorer):
        """Test sources score with three+ sources"""
        context = [
            {'filename': 'doc1.pdf'},
            {'filename': 'doc2.pdf'},
            {'filename': 'doc3.pdf'}
        ]
        score = scorer._calculate_sources_score(context, "Answer")
        assert score >= 0.6  # Base score for 3+ sources

    def test_citation_bonus(self, scorer):
        """Test citation bonus when sources are mentioned"""
        context = [
            {'filename': 'doc1.pdf'},
            {'filename': 'doc2.pdf'}
        ]
        answer = "According to doc1.pdf and doc2.pdf, the answer is..."
        score = scorer._calculate_sources_score(context, answer)
        assert score > 0.7  # Higher due to citations


class TestSpecificityScore:
    """Tests for specificity score calculation"""

    def test_code_blocks_bonus(self, scorer):
        """Test specificity with code blocks"""
        answer = """
        Here is an example:
        ```python
        def hello():
            print("Hello")
        ```
        """
        score = scorer._calculate_specificity_score(answer)
        assert score >= 0.3  # Code block bonus

    def test_numbers_bonus(self, scorer):
        """Test specificity with numbers"""
        answer = "The version is 3.9.0 and was released in 2020"
        score = scorer._calculate_specificity_score(answer)
        assert score >= 0.2  # Numbers bonus

    def test_examples_bonus(self, scorer):
        """Test specificity with examples"""
        answer = "예시: 다음과 같은 경우에 사용합니다"
        score = scorer._calculate_specificity_score(answer)
        assert score >= 0.3  # Example bonus

    def test_vague_words_penalty(self, scorer):
        """Test penalty for vague language"""
        answer = "아마도 대략 일반적으로 이것은 보통 그럴 것 같습니다"
        score = scorer._calculate_specificity_score(answer)
        # Multiple vague words should reduce score
        assert score < 0.5

    def test_specific_answer(self, scorer):
        """Test high specificity answer"""
        answer = """
        The function returns 42 as defined in version 2.0.
        예시:
        ```python
        result = calculate()
        ```
        """
        score = scorer._calculate_specificity_score(answer)
        assert score > 0.7


class TestConfidenceLevel:
    """Tests for confidence level classification"""

    def test_high_confidence(self, scorer):
        """Test high confidence level (>= 0.75)"""
        assert scorer._get_confidence_level(0.75) == 'high'
        assert scorer._get_confidence_level(0.85) == 'high'
        assert scorer._get_confidence_level(1.0) == 'high'

    def test_medium_confidence(self, scorer):
        """Test medium confidence level (0.50-0.75)"""
        assert scorer._get_confidence_level(0.50) == 'medium'
        assert scorer._get_confidence_level(0.65) == 'medium'
        assert scorer._get_confidence_level(0.74) == 'medium'

    def test_low_confidence(self, scorer):
        """Test low confidence level (< 0.50)"""
        assert scorer._get_confidence_level(0.0) == 'low'
        assert scorer._get_confidence_level(0.25) == 'low'
        assert scorer._get_confidence_level(0.49) == 'low'


class TestRecommendations:
    """Tests for recommendation generation"""

    def test_high_score_recommendation(self, scorer):
        """Test recommendation for high score"""
        rec = scorer._generate_recommendation(0.85, 0.9, 0.8, 0.9)
        assert "신뢰도가 높습니다" in rec
        assert "신뢰하고 사용" in rec

    def test_low_relevance_recommendation(self, scorer):
        """Test recommendation for low relevance"""
        rec = scorer._generate_recommendation(0.5, 0.4, 0.7, 0.7)
        assert "관련도가 낮습니다" in rec

    def test_low_coverage_recommendation(self, scorer):
        """Test recommendation for low coverage"""
        rec = scorer._generate_recommendation(0.5, 0.7, 0.3, 0.7)
        assert "불완전" in rec or "추가 질문" in rec

    def test_low_sources_recommendation(self, scorer):
        """Test recommendation for low sources"""
        rec = scorer._generate_recommendation(0.5, 0.7, 0.7, 0.3)
        assert "문서" in rec or "업로드" in rec

    def test_medium_score_default_recommendation(self, scorer):
        """Test default recommendation for medium score"""
        rec = scorer._generate_recommendation(0.6, 0.6, 0.6, 0.6)
        assert "중간 수준" in rec or "추가 확인" in rec


class TestCalculateConfidence:
    """Tests for overall confidence calculation"""

    def test_high_confidence_answer(self, scorer, sample_context_high_relevance):
        """Test high confidence scenario"""
        answer = """
        # Python 프로그래밍

        Python은 다음과 같은 특징을 가집니다:
        - 간결한 문법
        - 풍부한 라이브러리
        - 버전 3.9 이상 권장

        예시:
        ```python
        def hello():
            print("Hello, World!")
        ```

        출처: doc1.pdf, doc2.pdf에서 확인
        """
        question = "Python 프로그래밍이 무엇인가요?"

        result = scorer.calculate_confidence(answer, sample_context_high_relevance, question)

        assert 'score' in result
        assert 'level' in result
        assert 'percentage' in result
        assert 'factors' in result
        assert 'recommendation' in result
        assert 'details' in result

        assert result['score'] > 0.6
        assert result['level'] in ['low', 'medium', 'high']
        assert result['percentage'] == int(result['score'] * 100)
        assert result['details']['num_sources'] == 3
        assert result['details']['has_code'] is True
        assert result['details']['has_examples'] is True

    def test_low_confidence_answer(self, scorer, sample_context_low_relevance):
        """Test low confidence scenario"""
        answer = "아마도 그럴 것 같습니다."
        question = "복잡한 기술적 질문?"

        result = scorer.calculate_confidence(answer, sample_context_low_relevance, question)

        assert result['score'] < 0.5
        assert result['level'] == 'low'
        assert len(result['recommendation']) > 0

    def test_no_context_answer(self, scorer):
        """Test answer with no context"""
        answer = "I don't have enough information."
        question = "What is this?"

        result = scorer.calculate_confidence(answer, [], question)

        assert result['score'] < 0.4  # Should be low without context
        assert result['details']['num_sources'] == 0

    def test_factor_components(self, scorer, sample_context_high_relevance):
        """Test that all factor components are present"""
        answer = "Sample answer with good structure"
        question = "Sample question"

        result = scorer.calculate_confidence(answer, sample_context_high_relevance, question)

        assert 'relevance' in result['factors']
        assert 'coverage' in result['factors']
        assert 'sources' in result['factors']
        assert 'specificity' in result['factors']

        # All factors should be in 0-1 range
        for factor_name, factor_score in result['factors'].items():
            assert 0 <= factor_score <= 1, f"{factor_name} score out of range: {factor_score}"

    def test_weighted_average(self, scorer):
        """Test weighted average calculation"""
        # Create scenario with known scores
        context = [
            {'filename': 'doc1.pdf', 'score': 0.9},
            {'filename': 'doc2.pdf', 'score': 0.85},
            {'filename': 'doc3.pdf', 'score': 0.95}
        ]

        answer = """
        Well-structured answer with good coverage.

        예시:
        ```code
        example
        ```

        Mentioned: doc1.pdf, doc2.pdf, doc3.pdf
        Contains version 2.0 and specific details.
        """
        question = "structured coverage example specific"

        result = scorer.calculate_confidence(answer, context, question)

        # Verify weighted calculation
        manual_score = (
            result['factors']['relevance'] * 0.40 +
            result['factors']['coverage'] * 0.25 +
            result['factors']['sources'] * 0.20 +
            result['factors']['specificity'] * 0.15
        )

        assert abs(result['score'] - manual_score) < 0.01


class TestHelperMethods:
    """Tests for helper methods"""

    def test_has_code_blocks_positive(self, scorer):
        """Test code block detection - positive"""
        text = """
        Example:
        ```python
        code here
        ```
        """
        assert scorer._has_code_blocks(text) is True

    def test_has_code_blocks_negative(self, scorer):
        """Test code block detection - negative"""
        text = "No code blocks here"
        assert scorer._has_code_blocks(text) is False

    def test_has_examples_positive(self, scorer):
        """Test example detection - positive cases"""
        test_cases = [
            "예시: 다음과 같습니다",
            "예제를 보여드리겠습니다",
            "For example, consider this",
            "다음과 같은 경우"
        ]
        for text in test_cases:
            assert scorer._has_examples(text) is True, f"Failed for: {text}"

    def test_has_examples_negative(self, scorer):
        """Test example detection - negative"""
        text = "This text has no indicators at all"
        assert scorer._has_examples(text) is False


class TestEdgeCases:
    """Tests for edge cases"""

    def test_empty_answer(self, scorer):
        """Test with empty answer"""
        result = scorer.calculate_confidence("", [], "question")
        assert result['score'] >= 0
        assert result['level'] == 'low'

    def test_very_long_answer(self, scorer):
        """Test with very long answer"""
        answer = "A" * 10000
        result = scorer.calculate_confidence(answer, [], "question")
        assert result['score'] >= 0
        assert result['details']['answer_length'] == 10000

    def test_unicode_content(self, scorer):
        """Test with Unicode content"""
        answer = "한글 답변입니다. 🎯 이모지도 포함되어 있습니다."
        context = [{'filename': '문서.pdf', 'score': 0.8}]
        question = "한글 질문?"

        result = scorer.calculate_confidence(answer, context, question)
        assert result['score'] >= 0
        assert result['level'] in ['low', 'medium', 'high']

    def test_context_without_scores(self, scorer):
        """Test context items without score field"""
        context = [
            {'filename': 'doc1.pdf'},  # No score field
            {'filename': 'doc2.pdf'}
        ]
        answer = "Answer"
        question = "Question"

        result = scorer.calculate_confidence(answer, context, question)
        # Should handle missing scores gracefully
        assert result['score'] >= 0

    def test_malformed_context(self, scorer):
        """Test with malformed context data"""
        context = [
            {},  # Empty dict
            {'score': 0.8},  # No filename
            {'filename': 'doc.pdf'}  # No score (will default to 0.0)
        ]
        answer = "Answer"
        question = "Question"

        # Should handle missing fields gracefully
        result = scorer.calculate_confidence(answer, context, question)
        assert 'score' in result
        assert result['score'] >= 0
