#!/usr/bin/env python3
"""
데이터 마이그레이션 스크립트: Single User → Multi User

v2.2.0 다중 사용자 시스템으로 전환하기 위한 데이터 마이그레이션 스크립트입니다.
기존 데이터를 기본 관리자 계정으로 이전하여 하위 호환성을 유지합니다.

사용법:
    python scripts/migrate_to_multiuser.py --admin-email admin@chatbot.com --admin-password SecureP@ssw0rd
"""

import asyncio
import argparse
import sys
import os
from pathlib import Path
from datetime import datetime
import uuid

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

# Redis 연결 (환경 변수에서 읽기)
import redis.asyncio as redis
from dotenv import load_dotenv

load_dotenv()

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "")


class MigrationManager:
    """마이그레이션 관리자"""

    def __init__(self, redis_client):
        self.redis = redis_client
        self.stats = {
            "documents": 0,
            "conversations": 0,
            "groups": 0,
            "vectors": 0,
            "errors": []
        }

    async def create_admin_user(self, email: str, password: str, username: str = "관리자"):
        """기본 관리자 계정 생성"""

        from src.auth.utils import hash_password

        print(f"\n📝 관리자 계정 생성 중... ({email})")

        # 기존 계정 확인
        existing_user_id = await self.redis.get(f"user:email:{email}")
        if existing_user_id:
            print(f"⚠️  이미 존재하는 이메일입니다. 기존 계정 사용: {existing_user_id}")
            return existing_user_id.decode()

        # 새 사용자 ID 생성
        user_id = str(uuid.uuid4())

        # 비밀번호 해싱
        password_hash = hash_password(password)

        # 사용자 데이터
        user_data = {
            "user_id": user_id,
            "email": email,
            "username": username,
            "password_hash": password_hash,
            "created_at": datetime.utcnow().isoformat(),
            "is_active": "True",
            "role": "admin",
            "failed_login_attempts": "0"
        }

        # Redis에 저장
        await self.redis.hset(f"user:{user_id}", mapping=user_data)
        await self.redis.set(f"user:email:{email}", user_id)

        print(f"✅ 관리자 계정 생성 완료: {user_id}")
        return user_id

    async def migrate_documents(self, admin_user_id: str, dry_run: bool = False):
        """문서 마이그레이션"""

        print("\n📄 문서 마이그레이션 시작...")

        # 기존 문서 키 패턴: document:*
        pattern = "document:*"
        count = 0

        async for old_key in self.redis.scan_iter(match=pattern):
            try:
                old_key_str = old_key.decode() if isinstance(old_key, bytes) else old_key

                # document:{filename} → user:{user_id}:document:{filename}
                filename = old_key_str.split(":")[-1]
                new_key = f"user:{admin_user_id}:document:{filename}"

                # 기존 데이터 조회
                old_data = await self.redis.hgetall(old_key)

                if not old_data:
                    print(f"⚠️  빈 문서 건너뜀: {old_key_str}")
                    continue

                # 새 데이터에 user_id 추가
                new_data = {}
                for k, v in old_data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    new_data[key] = value

                new_data["user_id"] = admin_user_id

                if not dry_run:
                    # 새 키로 복사
                    await self.redis.hset(new_key, mapping=new_data)
                    print(f"  ✓ {old_key_str} → {new_key}")
                else:
                    print(f"  [DRY RUN] {old_key_str} → {new_key}")

                count += 1

            except Exception as e:
                error_msg = f"문서 마이그레이션 실패: {old_key_str} - {str(e)}"
                print(f"  ❌ {error_msg}")
                self.stats["errors"].append(error_msg)

        self.stats["documents"] = count
        print(f"✅ 문서 마이그레이션 완료: {count}개")

    async def migrate_conversations(self, admin_user_id: str, dry_run: bool = False):
        """대화 마이그레이션"""

        print("\n💬 대화 마이그레이션 시작...")

        # 기존 대화 키 패턴: conversation:*
        pattern = "conversation:*"
        count = 0

        async for old_key in self.redis.scan_iter(match=pattern):
            try:
                old_key_str = old_key.decode() if isinstance(old_key, bytes) else old_key

                # conversation:{conv_id} → user:{user_id}:conversation:{conv_id}
                conv_id = old_key_str.split(":")[-1]
                new_key = f"user:{admin_user_id}:conversation:{conv_id}"

                # 기존 데이터 조회
                old_data = await self.redis.hgetall(old_key)

                if not old_data:
                    continue

                # 새 데이터에 user_id 추가
                new_data = {}
                for k, v in old_data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    new_data[key] = value

                new_data["user_id"] = admin_user_id

                if not dry_run:
                    await self.redis.hset(new_key, mapping=new_data)
                    print(f"  ✓ {old_key_str} → {new_key}")
                else:
                    print(f"  [DRY RUN] {old_key_str} → {new_key}")

                count += 1

            except Exception as e:
                error_msg = f"대화 마이그레이션 실패: {old_key_str} - {str(e)}"
                print(f"  ❌ {error_msg}")
                self.stats["errors"].append(error_msg)

        self.stats["conversations"] = count
        print(f"✅ 대화 마이그레이션 완료: {count}개")

    async def migrate_groups(self, admin_user_id: str, dry_run: bool = False):
        """그룹 마이그레이션"""

        print("\n📂 그룹 마이그레이션 시작...")

        # 기존 그룹 키 패턴: group:*
        pattern = "group:*"
        count = 0

        async for old_key in self.redis.scan_iter(match=pattern):
            try:
                old_key_str = old_key.decode() if isinstance(old_key, bytes) else old_key

                # group:{group_id} → user:{user_id}:group:{group_id}
                group_id = old_key_str.split(":")[-1]
                new_key = f"user:{admin_user_id}:group:{group_id}"

                # 기존 데이터 조회
                old_data = await self.redis.hgetall(old_key)

                if not old_data:
                    continue

                # 새 데이터에 user_id 추가
                new_data = {}
                for k, v in old_data.items():
                    key = k.decode() if isinstance(k, bytes) else k
                    value = v.decode() if isinstance(v, bytes) else v
                    new_data[key] = value

                new_data["user_id"] = admin_user_id

                if not dry_run:
                    await self.redis.hset(new_key, mapping=new_data)
                    print(f"  ✓ {old_key_str} → {new_key}")
                else:
                    print(f"  [DRY RUN] {old_key_str} → {new_key}")

                count += 1

            except Exception as e:
                error_msg = f"그룹 마이그레이션 실패: {old_key_str} - {str(e)}"
                print(f"  ❌ {error_msg}")
                self.stats["errors"].append(error_msg)

        self.stats["groups"] = count
        print(f"✅ 그룹 마이그레이션 완료: {count}개")

    async def migrate_vectors(self, admin_user_id: str, dry_run: bool = False):
        """벡터 인덱스 마이그레이션"""

        print("\n🔍 벡터 인덱스 마이그레이션 시작...")
        print("⚠️  주의: 벡터 인덱스 재구축은 시간이 걸릴 수 있습니다")

        # 기존 벡터 키 패턴: vector:* (또는 프로젝트에 맞게 조정)
        # 실제 벡터 저장 패턴에 따라 수정 필요
        pattern = "idx:*"  # Redis Search 인덱스 패턴
        count = 0

        # TODO: 실제 벡터 마이그레이션 로직 구현
        # 벡터 인덱스 재구축이 필요할 수 있음

        print(f"⚠️  벡터 인덱스 마이그레이션은 수동으로 진행해야 합니다")
        print(f"   다음 명령어를 실행하세요:")
        print(f"   python scripts/rebuild_vector_index.py --user-id {admin_user_id}")

        self.stats["vectors"] = count

    async def cleanup_old_keys(self, dry_run: bool = False):
        """기존 키 정리 (선택 사항)"""

        print("\n🧹 기존 키 정리...")

        if dry_run:
            print("  [DRY RUN] 실제 삭제는 --no-dry-run 옵션을 사용하세요")
            return

        # 사용자 확인
        confirm = input("⚠️  기존 키를 삭제하시겠습니까? (yes/no): ")
        if confirm.lower() != "yes":
            print("  취소되었습니다")
            return

        patterns = ["document:*", "conversation:*", "group:*"]
        total_deleted = 0

        for pattern in patterns:
            count = 0
            async for old_key in self.redis.scan_iter(match=pattern):
                await self.redis.delete(old_key)
                count += 1

            print(f"  ✓ {pattern} 삭제 완료: {count}개")
            total_deleted += count

        print(f"✅ 총 {total_deleted}개 키 삭제 완료")

    def print_summary(self):
        """마이그레이션 결과 요약 출력"""

        print("\n" + "="*60)
        print("📊 마이그레이션 결과 요약")
        print("="*60)
        print(f"  📄 문서:    {self.stats['documents']:>6}개")
        print(f"  💬 대화:    {self.stats['conversations']:>6}개")
        print(f"  📂 그룹:    {self.stats['groups']:>6}개")
        print(f"  🔍 벡터:    {self.stats['vectors']:>6}개")
        print(f"  ❌ 오류:    {len(self.stats['errors']):>6}개")
        print("="*60)

        if self.stats["errors"]:
            print("\n⚠️  발생한 오류:")
            for error in self.stats["errors"]:
                print(f"  - {error}")


async def main():
    """메인 함수"""

    parser = argparse.ArgumentParser(
        description="v2.2.0 다중 사용자 시스템 데이터 마이그레이션 스크립트"
    )
    parser.add_argument(
        "--admin-email",
        required=True,
        help="관리자 계정 이메일"
    )
    parser.add_argument(
        "--admin-password",
        required=True,
        help="관리자 계정 비밀번호 (최소 8자, 대소문자+숫자+특수문자 포함)"
    )
    parser.add_argument(
        "--admin-username",
        default="관리자",
        help="관리자 계정 사용자명 (기본: 관리자)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 변경 없이 시뮬레이션만 실행"
    )
    parser.add_argument(
        "--cleanup",
        action="store_true",
        help="마이그레이션 후 기존 키 삭제 (주의: 복구 불가능)"
    )

    args = parser.parse_args()

    print("="*60)
    print("🚀 v2.2.0 데이터 마이그레이션 스크립트")
    print("="*60)
    print(f"관리자 이메일: {args.admin_email}")
    print(f"관리자 사용자명: {args.admin_username}")
    print(f"Dry Run: {'예' if args.dry_run else '아니오'}")
    print(f"기존 키 삭제: {'예' if args.cleanup else '아니오'}")
    print("="*60)

    if args.dry_run:
        print("\n⚠️  DRY RUN 모드: 실제 변경이 발생하지 않습니다")
    else:
        print("\n⚠️  실제 데이터 마이그레이션을 시작합니다")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ 취소되었습니다")
            return

    # Redis 연결
    redis_client = await redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD if REDIS_PASSWORD else None,
        decode_responses=False  # bytes로 받아서 처리
    )

    try:
        # 연결 테스트
        await redis_client.ping()
        print(f"\n✅ Redis 연결 성공: {REDIS_HOST}:{REDIS_PORT}")

        # 마이그레이션 관리자 생성
        manager = MigrationManager(redis_client)

        # 1. 관리자 계정 생성
        admin_user_id = await manager.create_admin_user(
            email=args.admin_email,
            password=args.admin_password,
            username=args.admin_username
        )

        # 2. 문서 마이그레이션
        await manager.migrate_documents(admin_user_id, dry_run=args.dry_run)

        # 3. 대화 마이그레이션
        await manager.migrate_conversations(admin_user_id, dry_run=args.dry_run)

        # 4. 그룹 마이그레이션
        await manager.migrate_groups(admin_user_id, dry_run=args.dry_run)

        # 5. 벡터 인덱스 마이그레이션 (경고 메시지만)
        await manager.migrate_vectors(admin_user_id, dry_run=args.dry_run)

        # 6. 기존 키 정리 (선택 사항)
        if args.cleanup:
            await manager.cleanup_old_keys(dry_run=args.dry_run)

        # 7. 결과 요약
        manager.print_summary()

        if args.dry_run:
            print("\n💡 실제 마이그레이션을 수행하려면 --dry-run 옵션을 제거하세요")
        else:
            print("\n✅ 마이그레이션 완료!")
            print(f"\n🔐 관리자 계정 정보:")
            print(f"   이메일: {args.admin_email}")
            print(f"   사용자 ID: {admin_user_id}")
            print(f"\n⚠️  다음 단계:")
            print(f"   1. .env 파일에서 ENABLE_AUTHENTICATION=true 설정")
            print(f"   2. 서버 재시작")
            print(f"   3. 관리자 계정으로 로그인 테스트")

    except Exception as e:
        print(f"\n❌ 마이그레이션 실패: {str(e)}")
        import traceback
        traceback.print_exc()

    finally:
        await redis_client.close()


if __name__ == "__main__":
    asyncio.run(main())
