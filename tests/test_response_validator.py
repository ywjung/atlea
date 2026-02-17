"""
Tests for ResponseValidator

📝 Changelog:
- 2025-12-30: Created comprehensive response validator tests
  - Forbidden pattern detection
  - Filename requirement validation
  - Auto-fix functionality
  - Statistics tracking
"""

import pytest
from src.response_validator import ResponseValidator


@pytest.fixture
def validator():
    """ResponseValidator instance with fresh statistics"""
    v = ResponseValidator()
    v.reset_statistics()
    return v


@pytest.fixture
def sample_context():
    """Sample context with filenames"""
    return [
        {'filename': 'python_guide.pdf', 'content': 'Python content'},
        {'filename': 'api_reference.pdf', 'content': 'API content'},
        {'filename': '설치가이드.pdf', 'content': 'Installation guide'}
    ]


class TestResponseValidator:
    """Tests for ResponseValidator initialization"""

    def test_initialization(self, validator):
        """Test validator initialization"""
        assert validator.violation_stats['total_checks'] == 0
        assert validator.violation_stats['total_violations'] == 0
        assert len(validator.violation_stats['violation_by_pattern']) == 0

    def test_forbidden_patterns_exist(self):
        """Test that forbidden patterns are defined"""
        assert len(ResponseValidator.FORBIDDEN_PATTERNS) > 0
        # Verify structure
        for pattern, description in ResponseValidator.FORBIDDEN_PATTERNS:
            assert isinstance(pattern, str)
            assert isinstance(description, str)


class TestValidateResponse:
    """Tests for response validation"""

    def test_valid_response_with_filename(self, validator, sample_context):
        """Test valid response with proper filename"""
        response = "[python_guide.pdf]에 따르면 Python은 훌륭한 언어입니다."
        filenames = [ctx['filename'] for ctx in sample_context]

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is True
        assert len(violations) == 0
        assert validator.violation_stats['total_checks'] == 1
        assert validator.violation_stats['total_violations'] == 0

    def test_invalid_response_document_number(self, validator):
        """Test invalid response with document number"""
        response = "문서 1을 기반으로 답변드립니다."
        filenames = ['test.pdf']

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is False
        assert len(violations) > 0
        assert any('문서 번호' in v for v in violations)

    def test_invalid_response_doc_n(self, validator):
        """Test invalid response with Doc N pattern"""
        response = "Doc 1에 따르면 이렇습니다."
        filenames = []

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is False
        assert len(violations) > 0

    def test_invalid_response_document_in_parentheses(self, validator):
        """Test invalid response with (문서 N)"""
        response = "이것은 (문서 2)에 있는 내용입니다."
        filenames = []

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is False
        assert any('괄호 안 문서 번호' in v for v in violations)

    def test_invalid_response_document_in_brackets(self, validator):
        """Test invalid response with [문서 N]"""
        response = "[문서 3]을 참고하세요."
        filenames = []

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is False
        assert any('대괄호 안 문서 번호' in v for v in violations)

    def test_missing_filename_warning(self, validator, sample_context):
        """Test warning when filename is not mentioned (info log only, still valid)"""
        response = "Python은 훌륭한 언어입니다."  # No filename mentioned
        filenames = [ctx['filename'] for ctx in sample_context]

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is True
        assert len(violations) == 0

    def test_vague_references(self, validator):
        """Test detection of vague references"""
        test_cases = [
            "해당 문서에 따르면 이렇습니다.",
            "제시된 문서는 말합니다.",
            "위 문서를 참고하세요."
        ]

        for response in test_cases:
            is_valid, violations = validator.validate_response(response, ['test.pdf'])
            assert is_valid is False, f"Should detect vague reference in: {response}"

    def test_response_without_context(self, validator):
        """Test validation when no context is provided"""
        response = "일반적인 답변입니다."
        filenames = []

        is_valid, violations = validator.validate_response(response, filenames)

        # Should be valid if no forbidden patterns
        assert is_valid is True

    def test_multiple_violations(self, validator):
        """Test response with multiple violations"""
        response = "문서 1을 기반으로 하고, 문서 2에 따르면, Doc 3에서..."
        filenames = []

        is_valid, violations = validator.validate_response(response, filenames)

        assert is_valid is False
        assert len(violations) > 2  # Multiple pattern matches


class TestAutoFixResponse:
    """Tests for auto-fix functionality"""

    def test_fix_document_number_basic(self, validator, sample_context):
        """Test fixing basic document number"""
        response = "문서 1을 기반으로 답변드립니다."

        fixed, fixes = validator.auto_fix_response(response, sample_context)

        assert '[python_guide.pdf]을 기반으로' in fixed
        assert len(fixes) > 0
        assert 'python_guide.pdf' in fixes[0]

    def test_fix_multiple_documents(self, validator, sample_context):
        """Test fixing multiple document numbers"""
        response = "문서 1에 따르면 이렇고, 문서 2는 저렇습니다."

        fixed, fixes = validator.auto_fix_response(response, sample_context)

        assert '[python_guide.pdf]' in fixed
        assert '[api_reference.pdf]' in fixed
        assert len(fixes) >= 2

    def test_fix_various_patterns(self, validator):
        """Test fixing various document number patterns"""
        context = [{'filename': 'test.pdf'}]

        test_cases = [
            ("문서 1을 기반으로", "[test.pdf]을 기반으로"),
            ("문서 1에 따르면", "[test.pdf]에 따르면"),
            ("문서 1는", "[test.pdf]는"),
            ("문서 1가", "[test.pdf]가"),
            ("문서 1의", "[test.pdf]의"),
            ("(문서 1)", "([test.pdf])"),
        ]

        for original, expected_substring in test_cases:
            fixed, _ = validator.auto_fix_response(original, context)
            assert expected_substring in fixed, f"Failed to fix: {original}"

    def test_fix_vague_references(self, validator, sample_context):
        """Test fixing vague references"""
        test_cases = [
            "해당 문서에 따르면",
            "제시된 문서는",
            "위 문서를"
        ]

        for response in test_cases:
            fixed, fixes = validator.auto_fix_response(response, sample_context)
            assert '[python_guide.pdf]' in fixed  # Should use first document
            assert len(fixes) > 0

    def test_no_fix_needed(self, validator, sample_context):
        """Test when no fix is needed"""
        response = "[python_guide.pdf]에 따르면 정확합니다."

        fixed, fixes = validator.auto_fix_response(response, sample_context)

        assert fixed == response  # Should be unchanged
        assert len(fixes) == 0

    def test_fix_with_empty_context(self, validator):
        """Test fixing with empty context"""
        response = "문서 1을 기반으로"

        fixed, fixes = validator.auto_fix_response(response, [])

        # Should not crash, but won't fix anything
        assert len(fixes) == 0

    def test_fix_preserves_korean(self, validator):
        """Test that fixing preserves Korean characters"""
        context = [{'filename': '한글파일.pdf'}]
        response = "문서 1은 한글로 작성되었습니다."

        fixed, fixes = validator.auto_fix_response(response, context)

        assert '[한글파일.pdf]' in fixed
        assert '한글로 작성되었습니다' in fixed


class TestStatistics:
    """Tests for statistics tracking"""

    def test_statistics_increment(self, validator):
        """Test that statistics are incremented"""
        response = "문서 1을 기반으로"
        filenames = []

        validator.validate_response(response, filenames)
        validator.validate_response(response, filenames)

        stats = validator.get_statistics()

        assert stats['total_checks'] == 2
        assert stats['total_violations'] == 2

    def test_statistics_pass_rate(self, validator, sample_context):
        """Test pass rate calculation"""
        filenames = [ctx['filename'] for ctx in sample_context]

        # 2 valid, 1 invalid
        validator.validate_response("[python_guide.pdf] is good", filenames)
        validator.validate_response("[api_reference.pdf] is also good", filenames)
        validator.validate_response("문서 1을 기반으로", filenames)

        stats = validator.get_statistics()

        assert stats['total_checks'] == 3
        # Note: Even valid ones might fail due to missing filename in response
        assert 'pass_rate' in stats

    def test_violation_by_pattern(self, validator):
        """Test violation counting by pattern"""
        # Trigger specific pattern multiple times
        validator.validate_response("문서 1을 기반으로", [])
        validator.validate_response("문서 2를 기반으로", [])

        stats = validator.get_statistics()

        assert 'violation_by_pattern' in stats
        # Should have counted violations
        assert len(stats['violation_by_pattern']) > 0

    def test_reset_statistics(self, validator):
        """Test statistics reset"""
        validator.validate_response("문서 1을 기반으로", [])
        validator.reset_statistics()

        stats = validator.get_statistics()

        assert stats['total_checks'] == 0
        assert stats['total_violations'] == 0
        assert len(stats['violation_by_pattern']) == 0

    def test_pass_rate_no_checks(self, validator):
        """Test pass rate with no checks"""
        stats = validator.get_statistics()

        assert stats['pass_rate'] == "0.0%"


class TestEdgeCases:
    """Tests for edge cases"""

    def test_empty_response(self, validator):
        """Test with empty response"""
        is_valid, violations = validator.validate_response("", [])
        assert is_valid is True  # No violations in empty string

    def test_very_long_response(self, validator, sample_context):
        """Test with very long response"""
        response = "[python_guide.pdf] " + "A" * 10000
        filenames = [ctx['filename'] for ctx in sample_context]

        is_valid, violations = validator.validate_response(response, filenames)
        # Should handle long text

    def test_special_characters_in_filename(self, validator):
        """Test with special characters in filename"""
        context = [{'filename': 'file-name_2025.v1.0.pdf'}]
        response = "문서 1에 따르면"

        fixed, fixes = validator.auto_fix_response(response, context)
        assert '[file-name_2025.v1.0.pdf]' in fixed

    def test_context_without_filename(self, validator):
        """Test context item without filename"""
        context = [{'content': 'Some content'}]  # No filename field
        response = "문서 1을 참고하세요"

        fixed, fixes = validator.auto_fix_response(response, context)
        # Should not crash

    def test_case_insensitive_pattern_matching(self, validator):
        """Test that pattern matching is case-insensitive"""
        response = "DOCUMENT 1에 따르면"

        is_valid, violations = validator.validate_response(response, [])
        assert is_valid is False  # Should detect uppercase DOC/DOCUMENT

    def test_fix_multiple_same_document(self, validator):
        """Test fixing same document number multiple times"""
        context = [{'filename': 'test.pdf'}]
        response = "문서 1은 중요하고 문서 1에 따르면 문서 1이 맞습니다"

        fixed, fixes = validator.auto_fix_response(response, context)

        # All instances should be fixed
        assert fixed.count('[test.pdf]') >= 3


class TestIntegration:
    """Integration tests for validate + fix workflow"""

    def test_validate_then_fix(self, validator, sample_context):
        """Test validation followed by fix"""
        response = "문서 1에 따르면 Python은 좋습니다."

        # First validate
        is_valid, violations = validator.validate_response(response, [])
        assert is_valid is False

        # Then fix
        fixed, fixes = validator.auto_fix_response(response, sample_context)

        # Validate fixed version
        filenames = [ctx['filename'] for ctx in sample_context]
        is_valid_after, violations_after = validator.validate_response(fixed, filenames)

        assert is_valid_after is True
        assert len(violations_after) == 0

    def test_fix_improves_validation(self, validator):
        """Test that auto-fix improves validation score"""
        context = [
            {'filename': 'report_a.pdf'},
            {'filename': 'report_b.pdf'}
        ]
        response = "문서 1을 기반으로 문서 2에 따르면 됩니다."

        # Validate before fix
        validator.reset_statistics()
        validator.validate_response(response, [ctx['filename'] for ctx in context])
        stats_before = validator.get_statistics()

        # Apply fix and validate
        fixed, _ = validator.auto_fix_response(response, context)
        validator.reset_statistics()
        validator.validate_response(fixed, [ctx['filename'] for ctx in context])
        stats_after = validator.get_statistics()

        # After fix should have fewer or equal violations
        assert stats_after['total_violations'] <= stats_before['total_violations']
