#!/usr/bin/env python3
"""
전체 문서 리인덱싱 스크립트
벡터 인덱스를 재생성하여 검색 기능 복구

사용법:
    python scripts/reindex_all_documents.py
"""

import sys
import os
from pathlib import Path

# 프로젝트 루트를 Python 경로에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.vector_db import VectorDB
from src.embeddings import EmbeddingModel
from src.document_processor import DocumentProcessor
from src.group_manager import GroupManager
from loguru import logger
import redis

# 환경 변수 설정
DATA_DIR = os.getenv("DATA_DIR", "./data")
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 512))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", 50))

def reindex_all_documents():
    """모든 문서 리인덱싱"""

    logger.info("="*60)
    logger.info("전체 문서 리인덱싱 시작")
    logger.info("="*60)

    # VectorDB 초기화
    logger.info("🔌 VectorDB 연결 중...")
    vector_db = VectorDB()

    # Embedding 모델 초기화
    logger.info("🤖 임베딩 모델 로딩 중...")
    embedding_model = EmbeddingModel()

    # DocumentProcessor 초기화
    logger.info("📄 문서 프로세서 초기화 중...")
    doc_processor = DocumentProcessor(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP
    )

    # GroupManager 초기화
    logger.info("📁 그룹 매니저 초기화 중...")
    group_manager = GroupManager(vector_db.client)

    # 데이터 디렉토리에서 모든 문서 파일 찾기
    data_path = Path(DATA_DIR)

    # 지원하는 파일 확장자
    extensions = ['.pdf', '.hwp', '.hwpx', '.txt', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']

    # 모든 파일 수집
    all_files = []
    for ext in extensions:
        files = list(data_path.glob(f'*{ext}'))
        all_files.extend(files)

    if not all_files:
        logger.warning(f"❌ {DATA_DIR} 디렉토리에 문서 파일이 없습니다.")
        return

    logger.info(f"📊 발견된 문서: {len(all_files)}개")

    # 현재 벡터 인덱스 상태 확인
    try:
        active_index = vector_db.client.get("index:active")
        if active_index:
            active_index = active_index.decode('utf-8')
            logger.info(f"📌 현재 활성 인덱스: {active_index}")

            # 현재 인덱스의 문서 수 확인
            current_docs = vector_db.client.keys(f"doc:{active_index}:*")
            logger.info(f"📈 현재 인덱스 문서 수: {len(current_docs)}개")
    except Exception as e:
        logger.warning(f"현재 인덱스 확인 실패: {e}")

    # 새 인덱스 생성
    logger.info("🔄 새 벡터 인덱스 생성 중...")
    import time
    timestamp = int(time.time())
    new_index_name = f"pdf_index_v{timestamp}"

    # VectorDB의 create_new_index 메서드 사용
    if not vector_db.create_new_index(new_index_name):
        logger.error("❌ 새 인덱스 생성 실패")
        return

    logger.success(f"✅ 새 인덱스 생성: {new_index_name}")

    # 각 문서 처리
    success_count = 0
    error_count = 0
    total_chunks = 0

    for idx, file_path in enumerate(all_files, 1):
        filename = file_path.name

        try:
            logger.info(f"[{idx}/{len(all_files)}] 처리 중: {filename}")

            # 문서 처리
            chunks = doc_processor.process_document(str(file_path))

            if not chunks:
                logger.warning(f"  ⚠️  {filename}: 청크 생성 실패")
                error_count += 1
                continue

            logger.info(f"  📑 청크 수: {len(chunks)}")

            # 임베딩 생성
            texts = [chunk["text"] for chunk in chunks]
            embeddings = embedding_model.encode(texts, batch_size=32, show_progress_bar=False)

            # chunks already contain the necessary metadata (filename, page, chunk_index)
            # Just ensure filename is set correctly
            for chunk in chunks:
                chunk["filename"] = filename
                if "page" not in chunk:
                    chunk["page"] = 0
                if "chunk_index" not in chunk:
                    chunk["chunk_index"] = 0

            # 벡터 DB에 저장 (새 인덱스에 추가)
            vector_db.add_documents(chunks, embeddings, target_index=new_index_name)

            # 그룹 매핑 확인 및 설정
            try:
                doc_group_key = f"doc:group:{filename}"
                group_id = vector_db.client.get(doc_group_key)

                if not group_id:
                    # 기본 그룹으로 설정
                    default_group_id = group_manager.get_default_group_id()
                    group_manager.assign_document(filename, default_group_id)
                    logger.info(f"  📎 기본 그룹 할당: {default_group_id}")
                else:
                    if isinstance(group_id, bytes):
                        group_id = group_id.decode('utf-8')
                    logger.info(f"  📎 기존 그룹 유지: {group_id}")
            except Exception as e:
                logger.warning(f"  ⚠️  그룹 매핑 오류: {e}")

            logger.success(f"  ✅ {filename} 인덱싱 완료 ({len(chunks)} chunks)")
            success_count += 1
            total_chunks += len(chunks)

        except Exception as e:
            logger.error(f"  ❌ {filename} 처리 실패: {e}")
            error_count += 1

    # 결과 요약
    logger.info("="*60)
    logger.info("리인덱싱 완료")
    logger.info("="*60)
    logger.success(f"✅ 성공: {success_count}개 문서")
    logger.error(f"❌ 실패: {error_count}개 문서")
    logger.info(f"📊 총 청크 수: {total_chunks}개")
    logger.info(f"📌 새 인덱스: {new_index_name}")

    # 새 인덱스 확인
    try:
        new_docs = vector_db.client.keys(f"doc:{new_index_name}:*")
        logger.info(f"📈 새 인덱스 문서 수: {len(new_docs)}개")
    except Exception as e:
        logger.warning(f"새 인덱스 확인 실패: {e}")

    logger.info("="*60)

if __name__ == "__main__":
    try:
        reindex_all_documents()
    except KeyboardInterrupt:
        logger.warning("\n⚠️  사용자에 의해 중단되었습니다.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ 리인덱싱 실패: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
