#!/usr/bin/env python3
"""
추천 질문 풀 생성 스크립트
Question pool generation script

문서를 분석하여 추천 질문 풀을 생성합니다.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import redis
import json
from loguru import logger
from typing import List, Dict
import random

# Redis 연결
redis_client = redis.Redis(
    host='localhost',
    port=6379,
    decode_responses=False,
    socket_connect_timeout=5
)

# 기본 질문 템플릿 (문서 기반 생성 실패 시 사용)
FALLBACK_QUESTIONS = [
    "이 문서의 주요 내용을 요약해주세요",
    "핵심 개념을 설명해주세요",
    "이 문서의 목적은 무엇인가요?",
    "주요 특징은 무엇인가요?",
    "실제 적용 사례는 어떻게 되나요?",
    "장점과 단점을 비교해주세요",
    "이 내용을 쉽게 설명해주세요",
    "관련된 추가 정보를 알려주세요",
]

def get_document_list() -> List[Dict]:
    """문서 목록 조회"""
    documents = []

    try:
        # 활성 인덱스 조회
        active_index = redis_client.get("index:active")
        if not active_index:
            logger.warning("활성 인덱스를 찾을 수 없습니다. 기본 인덱스 사용")
            # 기본 패턴으로 검색
            for key in redis_client.scan_iter(match="doc:*", count=100):
                key_str = key.decode('utf-8')
                if ':hash:' in key_str or ':group:' in key_str:
                    continue

                # 파일명 추출
                parts = key_str.split(':')
                if len(parts) >= 2:
                    doc_id = parts[-1]
                    doc_data = redis_client.hgetall(key)
                    if doc_data and b'filename' in doc_data:
                        documents.append({
                            'id': doc_id,
                            'filename': doc_data[b'filename'].decode('utf-8')
                        })
        else:
            index_name = active_index.decode('utf-8')
            logger.info(f"활성 인덱스: {index_name}")

            # 활성 인덱스의 문서 조회
            for key in redis_client.scan_iter(match=f"doc:{index_name}:*", count=100):
                key_str = key.decode('utf-8')
                if ':hash:' in key_str or ':group:' in key_str:
                    continue

                doc_data = redis_client.hgetall(key)
                if doc_data and b'filename' in doc_data:
                    doc_id = key_str.split(':')[-1]
                    documents.append({
                        'id': doc_id,
                        'filename': doc_data[b'filename'].decode('utf-8')
                    })

    except Exception as e:
        logger.error(f"문서 목록 조회 실패: {e}")

    return documents

def get_unique_filenames(documents: List[Dict]) -> List[str]:
    """고유한 파일명 목록 추출"""
    filenames = set()
    for doc in documents:
        filenames.add(doc['filename'])
    return sorted(list(filenames))

def generate_questions_from_documents(filenames: List[str]) -> List[str]:
    """문서 기반 질문 생성"""
    questions = []

    # 문서별 질문 템플릿
    templates = [
        "{filename}의 주요 내용을 요약해주세요",
        "{filename}에서 다루는 핵심 개념은 무엇인가요?",
        "{filename}의 목적과 배경을 설명해주세요",
        "{filename}에 나온 주요 데이터나 통계를 알려주세요",
        "{filename}의 결론 부분을 설명해주세요",
    ]

    # 각 문서마다 1-2개 질문 생성
    for filename in filenames[:10]:  # 최대 10개 문서
        # 파일명 정리 (확장자 제거)
        clean_name = filename.rsplit('.', 1)[0]

        # 랜덤하게 템플릿 선택
        template = random.choice(templates)
        question = template.format(filename=clean_name)
        questions.append(question)

    # 일반적인 질문 추가
    general_questions = [
        "전체 문서에서 공통적으로 다루는 주제는 무엇인가요?",
        "가장 최근 문서의 주요 내용을 알려주세요",
        "여러 문서를 비교해서 차이점을 설명해주세요",
    ]
    questions.extend(general_questions)

    return questions

def save_question_pool(questions: List[str], pool_name: str = "default"):
    """질문 풀을 Redis에 저장"""
    try:
        pool_key = f"question:pool:{pool_name}"

        # JSON으로 저장
        pool_data = json.dumps(questions, ensure_ascii=False)
        redis_client.set(pool_key, pool_data)

        # TTL 설정 (7일)
        redis_client.expire(pool_key, 7 * 24 * 3600)

        logger.success(f"✅ 질문 풀 저장 완료: {len(questions)}개 질문")
        return True

    except Exception as e:
        logger.error(f"질문 풀 저장 실패: {e}")
        return False

def main():
    """메인 실행 함수"""
    logger.info("🔍 문서 분석 및 질문 풀 생성 시작...")

    # 문서 목록 조회
    documents = get_document_list()

    if not documents:
        logger.warning("⚠️  문서를 찾을 수 없습니다. Fallback 질문만 사용합니다.")
        questions = FALLBACK_QUESTIONS
    else:
        logger.info(f"📊 발견된 문서 청크: {len(documents)}개")

        # 고유 파일명 추출
        filenames = get_unique_filenames(documents)
        logger.info(f"📁 고유 파일: {len(filenames)}개")

        # 파일 목록 출력
        print("\n발견된 문서:")
        print("-" * 80)
        for i, filename in enumerate(filenames[:20], 1):
            print(f"{i}. {filename}")
        if len(filenames) > 20:
            print(f"... 외 {len(filenames) - 20}개")
        print()

        # 질문 생성
        logger.info("💡 질문 생성 중...")
        questions = generate_questions_from_documents(filenames)

        # Fallback 질문 추가
        questions.extend(FALLBACK_QUESTIONS)

        # 중복 제거
        questions = list(dict.fromkeys(questions))

    # 생성된 질문 출력
    print("\n생성된 질문 풀:")
    print("=" * 80)
    for i, question in enumerate(questions, 1):
        print(f"{i}. {question}")
    print()

    logger.info(f"📝 총 {len(questions)}개 질문 생성")

    # 저장 여부 확인
    response = input("\nRedis에 저장하시겠습니까? (Y/n): ")

    if response.lower() == 'n':
        logger.info("❌ 저장이 취소되었습니다.")
        return

    # Redis에 저장
    if save_question_pool(questions):
        logger.success("✅ 질문 풀이 성공적으로 생성되었습니다!")
        logger.info("💡 웹 페이지를 새로고침하면 새로운 추천 질문이 표시됩니다.")
    else:
        logger.error("❌ 질문 풀 저장에 실패했습니다.")
        sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ 사용자가 작업을 중단했습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 오류 발생: {e}", exc_info=True)
        sys.exit(1)
