#!/usr/bin/env python3
"""
手动测试Greenhouse API
尝试找到正确的board tokens
"""
import asyncio
import aiohttp
import ssl


async def test_board_token(token: str):
    """测试board token"""
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    
    # Disable SSL verification for development
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=ssl_context, timeout=aiohttp.ClientTimeout(total=10)) as response:
                if response.status == 200:
                    data = await response.json()
                    jobs = data.get('jobs', data) if isinstance(data, dict) else data
                    if isinstance(jobs, list):
                        print(f"✅ {token}: 找到 {len(jobs)} 个职位")
                        return True
                    else:
                        print(f"⚠️  {token}: 响应格式异常")
                else:
                    print(f"❌ {token}: HTTP {response.status}")
    except Exception as e:
        print(f"❌ {token}: {e}")
    
    return False


async def main():
    """测试常见的board tokens"""
    
    # 这些是已知使用Greenhouse的公司和可能的tokens
    test_tokens = [
        # Airbnb
        ('Airbnb', ['airbnb', 'airbnbcareers', 'careers-airbnb']),
        
        # Stripe
        ('Stripe', ['stripe', 'stripecareers', 'stripe-2']),
        
        # GitLab - 已知使用Greenhouse
        ('GitLab', ['gitlab', 'gitlab-2']),
        
        # Coinbase
        ('Coinbase', ['coinbase', 'coinbase-2', 'coinbasecareers']),
        
        # Figma
        ('Figma', ['figma', 'figmacareers']),
        
        # Notion  
        ('Notion', ['notion', 'notioncareers']),
    ]
    
    print("🔍 开始测试 Greenhouse board tokens...\n")
    
    for company, tokens in test_tokens:
        print(f"\n{company}:")
        for token in tokens:
            await test_board_token(token)
            await asyncio.sleep(0.5)


if __name__ == '__main__':
    asyncio.run(main())
