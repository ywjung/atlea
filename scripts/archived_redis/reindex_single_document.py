#!/usr/bin/env python3
"""
단일 문서 재인덱싱 스크립트
특정 문서만 재인덱싱하여 RediSearch 인덱스에 추가

사용법:
    python scripts/reindex_single_document.py <filename>
    python scripts/reindex_single_document.py spring-boot-reference.pdf
"""

import sys
import os
import asyncio
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.embeddings import EmbeddingManager
from src.document_processor import DocumentProcessor
from src.cache_manager import CacheManager
import redis

async def reindex_single_document(filename: str):
    """단일 문서 재인덱싱"""

    print("="*80)
    print(f"단일 문서 재인덱싱: {filename}")
    print("="*80)

    # 환경 변수 설정
    DATA_DIR = os.getenv("DATA_DIR", "./data")
    data_path = Path(DATA_DIR)

    # 파일 존재 확인
    file_path = data_path / filename
    if not file_path.exists():
        print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
        return False

    print(f"\n✅ 파일 발견: {file_path}")
    print(f"   크기: {file_path.stat().st_size / (1024*1024):.2f} MB")

    # Redis 연결
    redis_client = redis.Redis(host='localhost', port=6379, decode_responses=True)

    # 그룹 확인
    doc_group_id = redis_client.get(f'doc:group:{filename}')
    if doc_group_id:
        group_data = redis_client.hgetall(f"group:{doc_group_id}")
        group_name = group_data.get('name', 'Unknown')
        print(f"   그룹: {group_name} ({doc_group_id})")
    else:
        print(f"   ⚠️  그룹 매핑 없음")

    # 활성 인덱스 확인
    active_index = redis_client.get("search:active_index")
    if active_index:
        print(f"\n📌 활성 인덱스: {active_index}")
    else:
        print(f"\n⚠️  활성 인덱스가 설정되지 않음")
        return False

    # 기존 청크 확인
    existing_chunks = redis_client.keys(f"{active_index}:chunk:*:{filename}")
    if existing_chunks:
        print(f"⚠️  기존 청크 발견: {len(existing_chunks)}개")
        response = input("기존 청크를 삭제하고 재인덱싱하시겠습니까? (y/N): ")
        if response.lower() != 'y':
            print("취소됨")
            return False

        # 기존 청크 삭제
        for chunk_key in existing_chunks:
            redis_client.delete(chunk_key)
        print(f"✅ 기존 청크 삭제 완료")

    try:
        # CacheManager 초기화
        cache_manager = CacheManager()

        # DocumentProcessor 초기화
        doc_processor = DocumentProcessor()

        # EmbeddingManager 초기화
        embeddings = EmbeddingManager(cache_manager=cache_manager)

        print(f"\n🔄 문서 처리 시작...")

        # 문서 처리
        chunks = await doc_processor.process_document(str(file_path))

        if not chunks:
            print(f"❌ 문서 처리 실패: 청크가 생성되지 않음")
            return False

        print(f"✅ 문서 처리 완료: {len(chunks)}개 청크 생성")

        # 임베딩 생성 및 인덱싱
        print(f"\n🔄 임베딩 생성 및 인덱싱 중...")

        # 청크별로 임베딩 생성
        chunk_texts = [chunk.get("text", "") for chunk in chunks]
        embeddings_result = await embeddings.create_embeddings(chunk_texts)

        if not embeddings_result:
            print(f"❌ 임베딩 생성 실패")
            return False

        print(f"✅ 임베딩 생성 완료: {len(embeddings_result)}개")

        # RediSearch에 추가
        print(f"\n🔄 RediSearch 인덱스에 추가 중...")

        # add_documents 호출
        result = await embeddings.add_documents(
            chunks=chunks,
            embeddings=embeddings_result,
            target_index=active_index
        )

        if result:
            print(f"✅ 인덱싱 완료!")

            # 검증
            new_chunks = redis_client.keys(f"{active_index}:chunk:*:{filename}")
            print(f"\n📊 인덱싱 결과:")
            print(f"   생성된 청크: {len(new_chunks)}개")

            # 전체 문서 수 확인
            print(f"\n🔍 전체 인덱스 확인 중...")
            # FT.AGGREGATE로 고유 문서 수 확인
            # (Redis command를 직접 실행해야 함)

            return True
        else:
            print(f"❌ 인덱싱 실패")
            return False

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    if len(sys.argv) < 2:
        print("사용법: python scripts/reindex_single_document.py <filename>")
        print("예제: python scripts/reindex_single_document.py spring-boot-reference.pdf")
        sys.exit(1)

    filename = sys.argv[1]
    success = await reindex_single_document(filename)

    if success:
        print("\n" + "="*80)
        print("✅ 재인덱싱 성공!")
        print("="*80)
        print("\n다음 명령어로 결과를 확인하세요:")
        print("docker exec chatbot_redis redis-cli FT.AGGREGATE pdf_index_v1768170155 \"*\" \\")
        print("  GROUPBY 1 @filename REDUCE COUNT 0 AS doc_count | head -1")
        sys.exit(0)
    else:
        print("\n" + "="*80)
        print("❌ 재인덱싱 실패")
        print("="*80)
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
