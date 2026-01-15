"""
Question Generation Service

Generates Korean questions from documents for autocomplete suggestions.
This service is optional and can be enabled/disabled via config.

Features:
- Generate 10+ questions per document
- Support for PDF and HWP files
- Parallel question generation
- Background processing without blocking startup
- Fallback questions for empty pool
"""

from pathlib import Path
from typing import List
import asyncio
import logging

logger = logging.getLogger(__name__)

# Global question pool storage
suggested_questions_pool: List[str] = []

# Global dependencies (injected from web_server.py)
llm = None
vector_db = None
DATA_DIR = None


def inject_dependencies(llm_instance, vector_db_instance, data_dir: str):
    """
    Inject dependencies from web_server.py

    Args:
        llm_instance: LLM model instance
        vector_db_instance: Vector database instance
        data_dir: Path to data directory
    """
    global llm, vector_db, DATA_DIR
    llm = llm_instance
    vector_db = vector_db_instance
    DATA_DIR = data_dir


async def _generate_questions_for_document(filename: str) -> list:
    """
    Generate Korean questions for a single document

    Args:
        filename: Name of the document file

    Returns:
        List of generated Korean questions
    """
    from mlx_lm import generate

    try:
        # Sample chunks from document
        docs = vector_db.sample_documents_by_filename(filename, limit=5)
        if not docs:
            return []

        # Create context from chunks
        context_text = "\n\n".join([
            f"{doc['text'][:800]}"
            for doc in docs[:5]
        ])

        # Generate questions using LLM
        system_content = "You must respond ONLY in Korean language. Never use English in your response."
        user_content = f"""다음은 "{filename}" 문서의 내용입니다. 이 문서를 읽고 한국어로 질문 12개를 생성하세요.

문서 내용:
{context_text}

다양한 유형의 질문을 만드세요:
1. 구체적 수치/기한: "임차보증금의 최대 한도는 얼마인가요?"
2. 절차/방법: "이사회 안건은 어떻게 제출하나요?"
3. 조건/기준: "징계 감경을 받을 수 있는 조건은 무엇인가요?"
4. 비교/차이: "문서규칙과 인사규정의 차이는 무엇인가요?"
5. 정의/개념: "전산업무관리지침에서 정의하는 시스템이란?"
6. 책임/담당: "비품 관리를 담당하는 부서는 어디인가요?"
7. 기한/기간: "연차 신청은 며칠 전까지 해야 하나요?"
8. 범위/대상: "출장비 지급 대상은 누구인가요?"

위 형식으로 한국어 질문 12개만 생성하세요 (번호 없이):"""

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]

        prompt = llm.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True
        )

        response = generate(
            llm.model,
            llm.tokenizer,
            prompt=prompt,
            max_tokens=1024
        )

        # Parse and filter questions
        lines = response.strip().split('\n')
        questions = []
        for line in lines:
            line = line.strip()
            if line and (line[0].isdigit() or line.startswith('-') or '?' in line):
                question = line.lstrip('0123456789.-) ').strip()
                if question and len(question) > 10 and question.endswith('?'):
                    # Filter: Only include questions with Korean characters
                    if any('\uac00' <= char <= '\ud7a3' for char in question):
                        questions.append(question)

        return questions

    except Exception as e:
        logger.warning(f"Failed to generate questions for {filename}: {e}")
        return []


async def generate_questions_pool():
    """
    Generate 10+ Korean questions per PDF/HWP document
    Questions are stored with document metadata for tracking
    """
    global suggested_questions_pool

    try:
        # Get list of PDF and HWP files
        data_path = Path(DATA_DIR)
        if not data_path.exists():
            return

        import itertools
        pdf_files = list(itertools.chain(
            data_path.glob("*.pdf"),
            data_path.glob("*.hwp")
        ))
        if not pdf_files:
            return

        logger.info(f"Generating questions for {len(pdf_files)} documents in parallel...")
        all_questions = []

        # Generate questions for each document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(pdf_file.name) for pdf_file in pdf_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for pdf_file, doc_questions in zip(pdf_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {pdf_file.name}: Failed - {doc_questions}")
                continue
            if doc_questions:
                all_questions.extend(doc_questions)
                logger.info(f"  • {pdf_file.name}: {len(doc_questions)} questions generated")

        # Store unique Korean-only questions in the pool
        suggested_questions_pool = list(set(all_questions))
        logger.info(f"Total unique questions: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions pool: {e}")
        # Set fallback questions
        suggested_questions_pool = [
            "이 문서의 주요 내용은 무엇인가요?",
            "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
            "이 문서를 간단히 요약해주세요.",
            "문서에서 다루는 핵심 주제는 무엇인가요?",
            "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?"
        ]


async def generate_questions_pool_background():
    """
    Background task wrapper for question generation
    Runs asynchronously without blocking server startup
    """
    try:
        logger.info("📝 Background: Generating question pool for all documents...")
        start_time = asyncio.get_event_loop().time()

        await generate_questions_pool()

        elapsed = asyncio.get_event_loop().time() - start_time
        logger.success(f"✅ Question pool ready! Generated {len(suggested_questions_pool)} questions in {elapsed:.1f}s")
    except Exception as e:
        logger.error(f"❌ Background question generation failed: {e}")
        logger.warning("App will continue with empty question pool")


async def generate_questions_for_new_documents(new_files: list):
    """
    Generate questions for newly added documents
    Called when new documents are detected and indexed
    """
    global suggested_questions_pool

    try:
        logger.info(f"Generating questions for {len(new_files)} new documents in parallel...")
        new_questions = []

        # Generate questions for each new document in parallel using asyncio.gather()
        tasks = [_generate_questions_for_document(filename) for filename in new_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for filename, doc_questions in zip(new_files, results):
            if isinstance(doc_questions, Exception):
                logger.warning(f"  • {filename}: Failed - {doc_questions}")
                continue
            if doc_questions:
                new_questions.extend(doc_questions)
                logger.info(f"  • {filename}: {len(doc_questions)} new questions generated")

        # Add new questions to existing pool (keep unique)
        suggested_questions_pool = list(set(suggested_questions_pool + new_questions))
        logger.success(f"Added {len(new_questions)} new questions. Total: {len(suggested_questions_pool)}")

    except Exception as e:
        logger.error(f"Failed to generate questions for new documents: {e}")


def get_fallback_questions() -> List[str]:
    """
    Get diverse fallback questions when pool is empty

    Returns:
        List of 30 diverse fallback questions covering various aspects
    """
    return [
        # General content questions
        "이 문서의 주요 내용은 무엇인가요?",
        "문서에서 가장 중요한 핵심 개념은 무엇인가요?",
        "이 문서를 간단히 요약해주세요.",
        "문서에서 다루는 핵심 주제는 무엇인가요?",
        "이 문서에서 얻을 수 있는 주요 정보는 무엇인가요?",

        # Detailed analysis questions
        "문서에서 설명하는 주요 개념을 자세히 설명해주세요.",
        "이 문서의 목적은 무엇인가요?",
        "문서에 나오는 중요한 용어들을 설명해주세요.",
        "이 문서가 다루는 범위는 어디까지인가요?",
        "문서에서 강조하는 핵심 메시지는 무엇인가요?",

        # Practical application questions
        "이 문서의 내용을 실제로 어떻게 활용할 수 있나요?",
        "문서에 나온 내용을 적용하려면 어떻게 해야 하나요?",
        "이 문서가 제시하는 해결책은 무엇인가요?",
        "문서에서 권장하는 방법은 무엇인가요?",
        "실무에 적용 가능한 내용이 있나요?",

        # Comparison and analysis questions
        "문서에서 비교하는 내용이 있나요?",
        "이 문서의 장단점은 무엇인가요?",
        "문서에서 언급된 사례나 예시를 알려주세요.",
        "문서의 내용과 관련된 배경 정보는 무엇인가요?",
        "이 문서와 관련된 다른 정보를 알려주세요.",

        # Specific details questions
        "문서에 나온 구체적인 수치나 데이터는 무엇인가요?",
        "문서에서 다루는 세부 항목들을 나열해주세요.",
        "이 문서에 포함된 주요 섹션은 무엇인가요?",
        "문서에서 제시하는 단계나 절차가 있나요?",
        "문서에 명시된 기준이나 요구사항은 무엇인가요?",

        # Context and implications questions
        "이 문서를 읽어야 하는 대상은 누구인가요?",
        "문서의 내용이 시사하는 바는 무엇인가요?",
        "이 문서와 관련하여 주의해야 할 점은 무엇인가요?",
        "문서에서 다루지 않은 내용은 무엇인가요?",
        "이 문서의 핵심을 한 문장으로 표현하면?"
    ]


def get_question_pool() -> List[str]:
    """
    Get current question pool

    Returns:
        List of questions from pool or fallback
    """
    return suggested_questions_pool if suggested_questions_pool else []
