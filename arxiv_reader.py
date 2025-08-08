#!/usr/bin/env python3
"""
arXiv Reader 主启动脚本
提供便捷的命令行界面
"""

import sys
import os
from pathlib import Path

# 添加 src 目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent / "src"))

from arxiv_reader.main import main as main_func
from arxiv_reader.scheduler import run_daemon, create_daemon_scheduler

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="arXiv Reader - 自动获取、翻译并推送 arXiv 论文",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  %(prog)s                      # 运行一次完整流程
  %(prog)s --test               # 测试所有连接
  %(prog)s --test-email         # 发送测试邮件
  %(prog)s --daemon             # 启动守护进程模式
  %(prog)s --preview            # 预览今日邮件
  %(prog)s --status             # 显示系统状态
  %(prog)s --categories cs.AI cs.CV  # 指定类别
        """
    )
    
    # 基本选项
    parser.add_argument("--config", default="config/config.yaml", 
                       help="配置文件路径 (默认: config/config.yaml)")
    
    # 操作模式
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument("--daemon", action="store_true", 
                           help="启动守护进程模式，定时执行任务")
    mode_group.add_argument("--test", action="store_true", 
                           help="测试所有服务连接 (arXiv, GPT, SMTP)")
    mode_group.add_argument("--test-email", action="store_true", 
                           help="发送测试邮件")
    mode_group.add_argument("--preview", action="store_true", 
                           help="预览今日邮件内容")
    mode_group.add_argument("--status", action="store_true", 
                           help="显示系统状态和统计信息")
    
    # 调度器选项
    schedule_group = parser.add_argument_group("调度器选项")
    schedule_group.add_argument("--schedule-test", action="store_true", 
                               help="测试调度配置")
    schedule_group.add_argument("--schedule-status", action="store_true", 
                               help="显示调度器状态")
    schedule_group.add_argument("--run-now", action="store_true", 
                               help="立即运行一次任务")
    
    # 工作流程选项
    workflow_group = parser.add_argument_group("工作流程选项")
    workflow_group.add_argument("--categories", nargs="+", 
                               help="指定要处理的 arXiv 类别 (如: cs.AI cs.CV)")
    workflow_group.add_argument("--force-retranslate", action="store_true", 
                               help="强制重新翻译已翻译的论文")
    workflow_group.add_argument("--skip-translation", action="store_true", 
                               help="跳过翻译步骤")
    workflow_group.add_argument("--skip-email", action="store_true", 
                               help="跳过邮件发送")
    
    args = parser.parse_args()
    
    # 检查配置文件是否存在
    if not Path(args.config).exists():
        print(f"❌ 配置文件不存在: {args.config}")
        print("请先创建配置文件，可参考 config/config.yaml 模板")
        return 1
    
    try:
        if args.daemon:
            # 守护进程模式
            print("🚀 启动 arXiv Reader 守护进程...")
            run_daemon(args.config)
            
        elif args.schedule_test or args.schedule_status or args.run_now:
            # 调度器相关操作
            scheduler = create_daemon_scheduler(args.config)
            
            if args.schedule_test:
                result = scheduler.test_schedule()
                print("📋 调度配置测试结果:")
                print(f"  配置有效: {'✅' if result['config_valid'] else '❌'}")
                print(f"  时区有效: {'✅' if result['timezone_valid'] else '❌'}")
                print(f"  时间格式有效: {'✅' if result['time_format_valid'] else '❌'}")
                
                if result["errors"]:
                    print("  错误列表:")
                    for error in result["errors"]:
                        print(f"    - {error}")
            
            elif args.schedule_status:
                status = scheduler.get_status()
                print("📊 调度器状态:")
                print(f"  启用状态: {'✅ 已启用' if status['enabled'] else '❌ 已禁用'}")
                print(f"  运行状态: {'✅ 运行中' if status['running'] else '❌ 已停止'}")
                print(f"  每日时间: {status['daily_time']}")
                print(f"  时区设置: {status['timezone']}")
                print(f"  下次运行: {status['next_run_time'] or '未安排'}")
                print(f"  上次运行: {status['last_run_time'] or '从未运行'}")
                
                if status['last_run_success'] is not None:
                    result_text = '✅ 成功' if status['last_run_success'] else '❌ 失败'
                    print(f"  上次结果: {result_text}")
            
            elif args.run_now:
                print("🚀 立即执行任务...")
                result = scheduler.run_now()
                
                if result["success"]:
                    print("✅ 任务执行成功")
                    print(f"  📚 获取论文: {result.get('papers_fetched', 0)} 篇")
                    print(f"  🌐 翻译论文: {result.get('papers_translated', 0)} 篇")
                    print(f"  📧 邮件发送: {'成功' if result.get('email_sent') else '失败'}")
                    print(f"  ⏱️  执行时间: {result.get('elapsed_time', 0):.2f} 秒")
                else:
                    print("❌ 任务执行失败")
                    for error in result.get("errors", []):
                        print(f"  💥 错误: {error}")
                    return 1
        
        else:
            # 使用原来的 main 函数，但先处理调度器选项
            original_argv = sys.argv[:]
            
            # 构建新的 argv 用于 main 函数
            new_argv = [sys.argv[0]]
            
            if args.config != "config/config.yaml":
                new_argv.extend(["--config", args.config])
            
            if args.test:
                new_argv.append("--test")
            elif args.test_email:
                new_argv.append("--test-email")
            elif args.preview:
                new_argv.append("--preview")
            elif args.status:
                new_argv.append("--status")
            
            if args.categories:
                new_argv.extend(["--categories"] + args.categories)
            if args.force_retranslate:
                new_argv.append("--force-retranslate")
            if args.skip_translation:
                new_argv.append("--skip-translation")
            if args.skip_email:
                new_argv.append("--skip-email")
            
            # 替换 sys.argv 并调用原 main 函数
            sys.argv = new_argv
            main_func()
            sys.argv = original_argv
    
    except KeyboardInterrupt:
        print("\n🛑 用户中断操作")
        return 1
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())