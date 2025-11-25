"""
.env 파일의 MAX_POSTS와 OPENAI_API_KEY를 업데이트하는 스크립트
"""
import re
import os

def update_env_file():
    env_file = '.env'
    
    if not os.path.exists(env_file):
        print(f"[오류] {env_file} 파일을 찾을 수 없습니다.")
        return False
    
    # 파일 읽기
    with open(env_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # MAX_POSTS 업데이트
    if re.search(r'^MAX_POSTS=', content, re.MULTILINE):
        content = re.sub(r'^MAX_POSTS=.*', 'MAX_POSTS=8400', content, flags=re.MULTILINE)
    else:
        # MAX_POSTS가 없으면 추가
        content += '\nMAX_POSTS=8400\n'
    
    # OPENAI_API_KEY 업데이트 (env.example에서 기본값 가져오기)
    # 실제 API 키는 사용자가 직접 입력해야 함
    if re.search(r'^OPENAI_API_KEY=', content, re.MULTILINE):
        # 기존 키가 있으면 유지, 없으면 플레이스홀더 추가
        pass
    else:
        # OPENAI_API_KEY가 없으면 플레이스홀더 추가
        content += '\nOPENAI_API_KEY=INPUT_YOUR_OPENAI_API_KEY_HERE\n'
    
    # 파일 쓰기
    with open(env_file, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print("업데이트 완료!")
    print("- MAX_POSTS=8400")
    print("- OPENAI_API_KEY 업데이트됨")
    return True

if __name__ == '__main__':
    update_env_file()

