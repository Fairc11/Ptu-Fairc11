"""
抖音抓取测试脚本 - 验证改进后 scaper 的 WAF 通过率和速度
用法: python test_scraper.py <抖音分享链接>
"""
import sys
import os
# 确保 stdout 能用 UTF-8
sys.stdout.reconfigure(encoding='utf-8', errors='replace') if hasattr(sys.stdout, 'reconfigure') else None
import asyncio
import time
sys.path.insert(0, "backend")

from app.services.scraper import DouyinScraper


async def test_single(scraper: DouyinScraper, url: str, method: str = "pw_api"):
    """测试单次抓取"""
    aweme_id = scraper._extract_aweme_id(url)
    if not aweme_id:
        # 先 resolve
        resolved = scraper._resolve_url(url)
        aweme_id = scraper._extract_aweme_id(resolved)
        if not aweme_id:
            print(f"  [FAIL] 无法提取 aweme_id")
            return None, 0

    start = time.perf_counter()
    try:
        if method == "pw_api":
            result = await scraper._scrape_via_pw_api(aweme_id, url)
        elif method == "api":
            result = await scraper._scrape_via_api(aweme_id)
        elif method == "full":
            result = await scraper.scrape(url)
        else:
            result = await scraper._scrape_via_playwright(url)
        elapsed = time.perf_counter() - start

        if result:
            print(f"  [OK] 成功 | {len(result.image_urls)}张图片 | 作者:{result.author} | 耗时:{elapsed:.1f}s")
            if result.music_url:
                print(f"    音乐: {result.music_title or '(有)'}")
            return result, elapsed
        else:
            print(f"  [FAIL] 失败 | 耗时:{elapsed:.1f}s")
            return None, elapsed
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  [FAIL] 异常: {e} | 耗时:{elapsed:.1f}s")
        return None, elapsed


async def test_pw_api_multirun(scraper: DouyinScraper, url: str, runs: int = 5):
    """测试 _scrape_via_pw_api 多轮成功率"""
    print(f"\n{'='*60}")
    print(f"测试: _scrape_via_pw_api × {runs} 轮")
    print(f"URL: {url}")
    print(f"{'='*60}")

    results = []
    times = []
    for i in range(runs):
        print(f"\n--- 第 {i+1}/{runs} 轮 ---")
        r, t = await test_single(scraper, url, "pw_api")
        results.append(r is not None)
        times.append(t)
        await asyncio.sleep(1)  # 轮间休息

    success = sum(results)
    avg_time = sum(times) / max(len(times) - results.count(False), 1)
    print(f"\n{'='*60}")
    print(f"结果: {success}/{runs} 成功 ({success/runs*100:.0f}%)")
    print(f"平均耗时(成功): {sum(t for r,t in zip(results,times) if r) / max(success,1):.1f}s")
    print(f"{'='*60}")


async def test_full_flow(scraper: DouyinScraper, url: str):
    """测试完整 scrape() 流程"""
    print(f"\n{'='*60}")
    print(f"测试: 完整 scrape() 流程")
    print(f"URL: {url}")
    print(f"{'='*60}")

    start = time.perf_counter()
    try:
        result = await scraper.scrape(url)
        elapsed = time.perf_counter() - start
        if result:
            print(f"  [OK] 成功 | 类型:{result.media_type.value} | {len(result.image_urls)}张图片")
            print(f"    标题:{result.title}")
            print(f"    作者:{result.author}")
            print(f"    耗时:{elapsed:.1f}s")
        else:
            print(f"  [FAIL] 失败 | 耗时:{elapsed:.1f}s")
    except Exception as e:
        elapsed = time.perf_counter() - start
        print(f"  ✗ 异常: {e} | 耗时:{elapsed:.1f}s")


async def main():
    if len(sys.argv) < 2:
        print("用法: python test_scraper.py <抖音分享链接> [轮数]")
        print("示例: python test_scraper.py 'https://v.douyin.com/xxxxx/' 5")
        sys.exit(1)

    url = sys.argv[1]
    runs = int(sys.argv[2]) if len(sys.argv) > 2 else 5

    print("初始化 scraper...")
    scraper = DouyinScraper()
    print(f"Cookies: sessionid={'YES' if scraper.cookies.get('sessionid') else 'NO'}, "
          f"sid_tt={'YES' if scraper.cookies.get('sid_tt') else 'NO'}")

    # 1. 多轮测试 _scrape_via_pw_api
    await test_pw_api_multirun(scraper, url, runs)

    # 2. 测试完整流程
    await test_full_flow(scraper, url)

    # 3. 清理
    await scraper.close()


if __name__ == "__main__":
    asyncio.run(main())
