#!/usr/bin/env python3
"""
전체 재인덱싱 스크립트 (직접 DB 접근 방식)
모든 data/ 디렉토리의 파일을 재인덱싱합니다.
"""

import sys
import os
import glob
from pathlib import Path
from datetime import datetime
import redis

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

from src.vector_db import VectorDB
from src.embeddings import EmbeddingModel
from src.cache_manager import CacheManager
from src.document_processor import DocumentProcessor

def process_file(file_path: str, vector_db, cache_manager, doc_processor, embedding_model):
    """단일 파일 처리"""
    filename = os.path.basename(file_path)

    print(f"📄 처리 중: {filename}")

    try:
        # 텍스트 추출
        text = doc_processor.extract_text_from_document(file_path)

        if not text or len(text.strip()) == 0:
            print(f"   ❌ 텍스트 추출 실패")
            return False

        print(f"   ✅ 텍스트 추출 완료: {len(text)} 문자")

        # 청크 분할 (DocumentProcessor의 text_splitter 사용)
        chunks = doc_processor.text_splitter.split_text(text)

        print(f"   📦 청크 생성: {len(chunks)}개")

        # 임베딩 생성
        embeddings = []
        for i, chunk in enumerate(chunks):
            if i % 10 == 0 and i > 0:
                print(f"   🔢 임베딩 생성 중: {i}/{len(chunks)}")
            emb = embedding_model.encode(chunk)[0]
            embeddings.append(emb)

        print(f"   ✅ 임베딩 생성 완료: {len(embeddings)}개")

        # VectorDB에 추가
        documents = []
        default_group_id = "default"  # 기본 그룹

        for i, chunk_text in enumerate(chunks):
            doc = {
                'text': chunk_text,
                'filename': filename,
                'source': file_path,
                'chunk_index': i,
                'total_chunks': len(chunks),
                'group_id': default_group_id,
                'version': 1
            }
            documents.append(doc)

        vector_db.add_documents(documents, embeddings)
        print(f"   💾 VectorDB 저장 완료")

        # 메타데이터 저장
        redis_client = cache_manager.redis
        doc_key = f"doc:version:{filename}:v1"
        file_size = os.path.getsize(file_path)

        redis_client.hset(doc_key, mapping={
            'filename': filename,
            'stored_path': file_path,
            'size': str(file_size),
            'indexed': 'True',
            'chunk_count': str(len(chunks)),
            'created_at': datetime.now().isoformat(),
            'version': '1'
        })

        redis_client.sadd('doc:files', filename)

        print(f"   ✅ 메타데이터 저장 완료")
        print("")

        return True

    except Exception as e:
        print(f"   ❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("=" * 60)
    print("전체 재인덱싱 시작")
    print("=" * 60)
    print(f"시작 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("")

    # 임베딩 모델 초기화
    print("🔧 임베딩 모델 초기화 중...")
    embedding_model = EmbeddingModel()
    print("   ✅ 초기화 완료")
    print("")

    # Redis 및 VectorDB 연결
    redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
    cache_manager = CacheManager(redis_client=redis_client, embedding_model=embedding_model)
    vector_db = VectorDB(host='localhost', port=6379, db=0)
    print("✅ Redis 및 VectorDB 연결 완료")
    print("")

    # 문서 프로세서 초기화
    print("🔧 문서 프로세서 초기화 중...")
    doc_processor = DocumentProcessor(chunk_size=1000, chunk_overlap=200)
    print("   ✅ 초기화 완료")
    print("")

    # data/ 디렉토리의 모든 파일 찾기
    file_patterns = [
        'data/*.pdf',
        'data/*.txt',
        'data/*.hwp',
        'data/*.hwpx',
        'data/*.doc',
        'data/*.docx'
    ]

    all_files = []
    for pattern in file_patterns:
        all_files.extend(glob.glob(pattern))

    print(f"📁 총 {len(all_files)}개 파일 발견")
    print("")

    # 기본 그룹 생성
    import uuid
    group_id = str(uuid.uuid4())  # 새 UUID 생성
    group_key = f"group:{group_id}"

    # 그룹 메타데이터 저장 (Hash)
    redis_client.hset(group_key, mapping={
        'id': group_id,
        'name': '기본',
        'description': '전체 재인덱싱 후 생성된 기본 그룹',
        'created_at': datetime.now().isoformat(),
        'document_count': '0',
        'org_id': 'default',
        'icon': '📁',
        'color': '#3B82F6'
    })

    # 기본 그룹 ID 저장 (String)
    redis_client.set('group:default', group_id)

    # 조직-그룹 매핑 추가
    redis_client.sadd('org:groups:default', group_id)  # 조직에 그룹 추가
    redis_client.sadd(f'group:orgs:{group_id}', 'default')  # 그룹에 조직 추가

    print(f"✅ 기본 그룹 생성: {group_id}")
    print(f"   조직에 할당: default")
    print("")

    # 파일 처리
    success_count = 0
    fail_count = 0

    for i, file_path in enumerate(all_files, 1):
        print(f"[{i}/{len(all_files)}] ", end='')
        if process_file(file_path, vector_db, cache_manager, doc_processor, embedding_model):
            success_count += 1

            # 그룹에 문서 추가
            filename = os.path.basename(file_path)
            redis_client.sadd(f"group:docs:{group_id}", filename)
            # 역방향 매핑 추가 (문서 → 그룹)
            redis_client.set(f"doc:group:{filename}", group_id)
        else:
            fail_count += 1

    # 그룹 문서 개수 업데이트
    redis_client.hset(f"group:{group_id}", 'document_count', str(success_count))

    print("")
    print("=" * 60)
    print("재인덱싱 완료")
    print("=" * 60)
    print(f"종료 시간: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"✅ 성공: {success_count}개")
    print(f"❌ 실패: {fail_count}개")
    print(f"📊 총 파일: {len(all_files)}개")
    if len(all_files) > 0:
        print(f"📈 성공률: {(success_count/len(all_files)*100):.1f}%")
    print("")
    print("✅ 모든 문서가 '기본' 그룹에 추가되었습니다")
    print("   관리자 페이지에서 그룹을 생성하고 문서를 이동하세요")
    print("")

if __name__ == '__main__':
    main()
