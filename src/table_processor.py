"""
Table Processor - 표 데이터 처리 모듈

문서에서 표(테이블) 구조를 인식하고 행 단위로 청킹합니다.
표 데이터는 일반 텍스트와 다르게 처리하여 검색 품질을 향상시킵니다.

📝 Changelog:
- 2026-01-22: 초기 구현
  - 마크다운 테이블 감지 및 파싱
  - HTML 테이블 감지 및 파싱
  - 행 단위 청킹
  - 표 메타데이터 보존
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field
from loguru import logger


@dataclass
class TableChunk:
    """표에서 추출한 청크"""
    content: str  # 청크 내용
    table_index: int  # 문서 내 표 인덱스
    row_index: int  # 표 내 행 인덱스
    headers: List[str]  # 표 헤더
    row_data: Dict[str, str]  # 헤더:값 매핑
    table_title: Optional[str] = None  # 표 제목 (있는 경우)
    original_format: str = "markdown"  # 원본 형식 (markdown/html)


@dataclass
class Table:
    """파싱된 표 구조"""
    headers: List[str]
    rows: List[List[str]]
    title: Optional[str] = None
    start_pos: int = 0
    end_pos: int = 0
    format: str = "markdown"


class TableProcessor:
    """
    문서에서 표를 감지하고 처리하는 프로세서

    마크다운과 HTML 형식의 표를 인식하여
    검색에 최적화된 청크로 변환합니다.
    """

    # 마크다운 테이블 패턴
    MD_TABLE_PATTERN = re.compile(
        r'^\|(.+)\|\s*\n\|[-:\|\s]+\|\s*\n((?:\|.+\|\s*\n?)+)',
        re.MULTILINE
    )

    # HTML 테이블 패턴
    HTML_TABLE_PATTERN = re.compile(
        r'<table[^>]*>(.*?)</table>',
        re.DOTALL | re.IGNORECASE
    )

    # HTML 행 패턴
    HTML_ROW_PATTERN = re.compile(
        r'<tr[^>]*>(.*?)</tr>',
        re.DOTALL | re.IGNORECASE
    )

    # HTML 셀 패턴 (th 또는 td)
    HTML_CELL_PATTERN = re.compile(
        r'<t[hd][^>]*>(.*?)</t[hd]>',
        re.DOTALL | re.IGNORECASE
    )

    def __init__(
        self,
        min_columns: int = 2,
        min_rows: int = 1,
        include_header_in_chunk: bool = True,
        chunk_mode: str = "row"  # "row" | "table" | "both"
    ):
        """
        TableProcessor 초기화

        Args:
            min_columns: 표로 인식할 최소 컬럼 수
            min_rows: 표로 인식할 최소 행 수
            include_header_in_chunk: 각 청크에 헤더 포함 여부
            chunk_mode: 청킹 모드
                - "row": 행 단위 청킹
                - "table": 표 전체를 하나의 청크로
                - "both": 표 전체 + 행 단위 모두 생성
        """
        self.min_columns = min_columns
        self.min_rows = min_rows
        self.include_header_in_chunk = include_header_in_chunk
        self.chunk_mode = chunk_mode

        logger.info(f"📊 TableProcessor initialized (mode: {chunk_mode})")

    def detect_tables(self, text: str) -> List[Table]:
        """
        텍스트에서 표를 감지

        Args:
            text: 처리할 텍스트

        Returns:
            감지된 Table 객체 리스트
        """
        tables = []

        # 마크다운 테이블 감지
        md_tables = self._detect_markdown_tables(text)
        tables.extend(md_tables)

        # HTML 테이블 감지
        html_tables = self._detect_html_tables(text)
        tables.extend(html_tables)

        # 위치 기준 정렬 (중복 제거를 위해)
        tables.sort(key=lambda t: t.start_pos)

        # 중복 위치 제거 (마크다운과 HTML이 겹치는 경우)
        unique_tables = []
        last_end = -1
        for table in tables:
            if table.start_pos >= last_end:
                unique_tables.append(table)
                last_end = table.end_pos

        logger.debug(f"📊 Detected {len(unique_tables)} tables in text")
        return unique_tables

    def _detect_markdown_tables(self, text: str) -> List[Table]:
        """마크다운 테이블 감지"""
        tables = []

        for match in self.MD_TABLE_PATTERN.finditer(text):
            try:
                header_line = match.group(1)
                body = match.group(2)

                # 헤더 파싱
                headers = [cell.strip() for cell in header_line.split('|') if cell.strip()]

                if len(headers) < self.min_columns:
                    continue

                # 행 파싱
                rows = []
                for line in body.strip().split('\n'):
                    if '|' in line:
                        cells = [cell.strip() for cell in line.split('|') if cell.strip()]
                        if cells:
                            rows.append(cells)

                if len(rows) < self.min_rows:
                    continue

                # 표 제목 추출 시도 (표 바로 위 줄)
                title = self._extract_table_title(text, match.start())

                tables.append(Table(
                    headers=headers,
                    rows=rows,
                    title=title,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    format="markdown"
                ))

            except Exception as e:
                logger.warning(f"Failed to parse markdown table: {e}")
                continue

        return tables

    def _detect_html_tables(self, text: str) -> List[Table]:
        """HTML 테이블 감지"""
        tables = []

        for match in self.HTML_TABLE_PATTERN.finditer(text):
            try:
                table_html = match.group(1)

                # 행 추출
                rows_data = []
                headers = []

                for row_match in self.HTML_ROW_PATTERN.finditer(table_html):
                    row_html = row_match.group(1)
                    cells = []

                    for cell_match in self.HTML_CELL_PATTERN.finditer(row_html):
                        cell_content = self._strip_html_tags(cell_match.group(1)).strip()
                        cells.append(cell_content)

                    if cells:
                        # 첫 번째 행은 헤더로 가정
                        if not headers:
                            headers = cells
                        else:
                            rows_data.append(cells)

                if len(headers) < self.min_columns:
                    continue

                if len(rows_data) < self.min_rows:
                    continue

                tables.append(Table(
                    headers=headers,
                    rows=rows_data,
                    title=None,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    format="html"
                ))

            except Exception as e:
                logger.warning(f"Failed to parse HTML table: {e}")
                continue

        return tables

    def _strip_html_tags(self, html: str) -> str:
        """HTML 태그 제거"""
        return re.sub(r'<[^>]+>', '', html)

    def _extract_table_title(self, text: str, table_start: int) -> Optional[str]:
        """표 제목 추출 (표 바로 위 줄)"""
        # 표 시작 위치 이전 텍스트에서 마지막 줄 추출
        preceding_text = text[:table_start].rstrip()

        if not preceding_text:
            return None

        # 마지막 줄 추출
        last_newline = preceding_text.rfind('\n')
        if last_newline == -1:
            last_line = preceding_text
        else:
            last_line = preceding_text[last_newline + 1:]

        last_line = last_line.strip()

        # 제목 패턴 확인 (마크다운 헤더 또는 일반 텍스트)
        if last_line and len(last_line) > 2 and len(last_line) < 100:
            # 마크다운 헤더 제거
            if last_line.startswith('#'):
                last_line = last_line.lstrip('#').strip()

            # 빈 줄이나 구분선이 아닌 경우만
            if last_line and not re.match(r'^[-=_*]+$', last_line):
                return last_line

        return None

    def extract_and_chunk(
        self,
        text: str,
        base_metadata: Optional[Dict] = None
    ) -> Tuple[str, List[Dict]]:
        """
        텍스트에서 표를 추출하고 청킹

        Args:
            text: 처리할 텍스트
            base_metadata: 기본 메타데이터

        Returns:
            (표가 제거된 텍스트, 표 청크 리스트)
        """
        base_metadata = base_metadata or {}

        # 표 감지
        tables = self.detect_tables(text)

        if not tables:
            return text, []

        # 표 청킹
        table_chunks = []
        for table_idx, table in enumerate(tables):
            chunks = self._chunk_table(table, table_idx, base_metadata)
            table_chunks.extend(chunks)

        # 표 영역을 텍스트에서 제거
        remaining_text = self._remove_tables_from_text(text, tables)

        logger.info(f"📊 Extracted {len(table_chunks)} chunks from {len(tables)} tables")

        return remaining_text, table_chunks

    def _chunk_table(
        self,
        table: Table,
        table_idx: int,
        base_metadata: Dict
    ) -> List[Dict]:
        """표를 청크로 변환"""
        chunks = []

        if self.chunk_mode in ["table", "both"]:
            # 표 전체를 하나의 청크로
            table_content = self._table_to_text(table)
            chunks.append({
                "text": table_content,
                "chunk_type": "table",
                "table_index": table_idx,
                "table_title": table.title,
                "table_headers": table.headers,
                "row_count": len(table.rows),
                "is_table": True,
                **base_metadata
            })

        if self.chunk_mode in ["row", "both"]:
            # 행 단위 청킹
            for row_idx, row in enumerate(table.rows):
                row_chunk = self._row_to_chunk(table, row, table_idx, row_idx, base_metadata)
                chunks.append(row_chunk)

        return chunks

    def _row_to_chunk(
        self,
        table: Table,
        row: List[str],
        table_idx: int,
        row_idx: int,
        base_metadata: Dict
    ) -> Dict:
        """행을 청크로 변환"""
        # 헤더-값 쌍 생성
        row_data = {}
        for i, header in enumerate(table.headers):
            if i < len(row):
                row_data[header] = row[i]
            else:
                row_data[header] = ""

        # 청크 텍스트 생성
        if self.include_header_in_chunk:
            # "헤더: 값" 형식
            content_parts = [f"{h}: {v}" for h, v in row_data.items() if v]
            content = " | ".join(content_parts)

            # 표 제목 추가
            if table.title:
                content = f"[{table.title}] {content}"
        else:
            content = " | ".join(row)

        return {
            "text": content,
            "chunk_type": "table_row",
            "table_index": table_idx,
            "row_index": row_idx,
            "table_title": table.title,
            "table_headers": table.headers,
            "row_data": row_data,
            "is_table": True,
            **base_metadata
        }

    def _table_to_text(self, table: Table) -> str:
        """표를 텍스트로 변환"""
        lines = []

        # 제목
        if table.title:
            lines.append(f"## {table.title}")

        # 헤더
        header_line = " | ".join(table.headers)
        lines.append(header_line)
        lines.append("-" * len(header_line))

        # 행
        for row in table.rows:
            row_line = " | ".join(row)
            lines.append(row_line)

        return "\n".join(lines)

    def _remove_tables_from_text(self, text: str, tables: List[Table]) -> str:
        """텍스트에서 표 영역 제거"""
        if not tables:
            return text

        # 역순으로 제거 (인덱스 유지를 위해)
        result = text
        for table in reversed(tables):
            result = result[:table.start_pos] + "\n[표 생략]\n" + result[table.end_pos:]

        return result


class NumberDataProcessor:
    """
    숫자 데이터 처리 프로세서

    표나 본문에서 숫자 데이터를 인식하고
    검색 친화적인 형태로 변환합니다.
    """

    # 숫자 패턴
    NUMBER_PATTERNS = {
        'currency': re.compile(r'[\$\€\£\¥\₩]?\s?[\d,]+(?:\.\d{2})?(?:\s?(?:원|달러|유로|엔|위안))?'),
        'percentage': re.compile(r'\d+(?:\.\d+)?%'),
        'date': re.compile(r'\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4}'),
        'quantity': re.compile(r'\d+(?:,\d{3})*(?:\.\d+)?(?:\s?(?:개|건|명|회|일|시간|분|초))?')
    }

    def __init__(self):
        """NumberDataProcessor 초기화"""
        logger.info("🔢 NumberDataProcessor initialized")

    def extract_numbers(self, text: str) -> Dict[str, List[str]]:
        """
        텍스트에서 숫자 데이터 추출

        Args:
            text: 처리할 텍스트

        Returns:
            카테고리별 추출된 숫자 데이터
        """
        results = {}

        for category, pattern in self.NUMBER_PATTERNS.items():
            matches = pattern.findall(text)
            if matches:
                results[category] = list(set(matches))  # 중복 제거

        return results

    def enhance_number_context(self, text: str) -> str:
        """
        숫자 데이터의 컨텍스트 강화

        숫자 주변에 컨텍스트 단어를 추가하여
        검색 가능성을 높입니다.

        Args:
            text: 원본 텍스트

        Returns:
            강화된 텍스트
        """
        # 화폐 패턴에 "금액", "비용" 등 추가
        enhanced = self.NUMBER_PATTERNS['currency'].sub(
            lambda m: f"{m.group(0)} (금액)",
            text
        )

        # 퍼센트 패턴에 "비율" 추가
        enhanced = self.NUMBER_PATTERNS['percentage'].sub(
            lambda m: f"{m.group(0)} (비율)",
            enhanced
        )

        return enhanced
