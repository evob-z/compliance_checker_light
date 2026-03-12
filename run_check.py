#!/usr/bin/env python3
"""运行合规检查"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent / "src"))

from compliance_checker.skill import ComplianceSkill


async def main():
    skill = ComplianceSkill()
    result = await skill.check(
        project_path='/test',
        requirements='检查是否有发票文件，验证签发日期是否在2026年3月10日前，检查是否有印章',
        project_period={'start': '2026-01', 'end': '2026-12'}
    )
    
    print('='*60)
    print('检查结果')
    print('='*60)
    print(result['issues_description'])
    print()
    print('检查摘要:')
    print(f"  文档数量: {result['document_count']}")
    print(f"  执行时间: {result['execution_time']:.2f}秒")
    print(f"  成功: {result['success']}")


if __name__ == "__main__":
    asyncio.run(main())
