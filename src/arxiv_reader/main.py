"""
主程序模块
整合各个功能模块，提供完整的工作流程
"""

import logging
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path

from .config import init_config, get_config
from .arxiv_fetcher import get_fetcher
from .translator import get_translator
from .email_sender import get_email_sender
from .storage import get_storage, PaperData


def setup_logging() -> None:
    """设置日志配置"""
    config = get_config()
    
    # 创建日志目录
    log_file = Path(config.logging.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 配置日志格式
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # 获取日志级别
    log_level = getattr(logging, config.logging.level.upper(), logging.INFO)
    
    # 配置根日志器
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[
            logging.FileHandler(config.logging.log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout) if config.logging.console_output else logging.NullHandler()
        ]
    )
    
    # 设置第三方库的日志级别
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('openai').setLevel(logging.WARNING)


class ArxivReader:
    """arXiv 读者主类"""
    
    def __init__(self, config_path: str = "config/config.yaml"):
        """
        初始化 arXiv 读者
        
        Args:
            config_path: 配置文件路径
        """
        # 初始化配置
        self.config = init_config(config_path)
        
        # 设置日志
        setup_logging()
        self.logger = logging.getLogger(__name__)
        
        # 初始化各个模块
        self.fetcher = get_fetcher()
        self.translator = get_translator()
        self.email_sender = get_email_sender()
        self.storage = get_storage()
        
        self.logger.info("arXiv Reader 初始化完成")

    def test_all_connections(self) -> Dict[str, bool]:
        """
        测试所有服务连接
        
        Returns:
            各服务的连接状态
        """
        self.logger.info("开始测试所有服务连接...")
        
        results = {}
        
        # 测试 GPT API 连接
        try:
            results['gpt_api'] = self.translator.test_connection()
        except Exception as e:
            self.logger.error(f"GPT API 连接测试失败: {e}")
            results['gpt_api'] = False
        
        # 测试邮件服务器连接
        try:
            results['email_smtp'] = self.email_sender.test_email_connection()
        except Exception as e:
            self.logger.error(f"邮件服务器连接测试失败: {e}")
            results['email_smtp'] = False
        
        # 测试 arXiv API (通过简单搜索)
        try:
            test_papers = self.fetcher.search_papers_by_category("cs.AI", max_results=1)
            results['arxiv_api'] = len(test_papers) > 0
        except Exception as e:
            self.logger.error(f"arXiv API 连接测试失败: {e}")
            results['arxiv_api'] = False
        
        self.logger.info(f"连接测试结果: {results}")
        return results

    def fetch_daily_papers(self, categories: Optional[List[str]] = None) -> Dict[str, List[PaperData]]:
        """
        获取每日论文
        
        Args:
            categories: 要获取的类别列表
            
        Returns:
            按类别分组的论文
        """
        self.logger.info("开始获取每日论文...")
        
        start_time = time.time()
        
        try:
            papers_by_category = self.fetcher.fetch_daily_papers(categories)
            
            total_papers = sum(len(papers) for papers in papers_by_category.values())
            elapsed_time = time.time() - start_time
            
            self.logger.info(f"论文获取完成: {total_papers} 篇论文，耗时 {elapsed_time:.2f} 秒")
            
            return papers_by_category
            
        except Exception as e:
            self.logger.error(f"获取每日论文失败: {e}")
            return {}

    def translate_papers(self, papers_by_category: Dict[str, List[PaperData]], 
                        force_retranslate: bool = False) -> int:
        """
        翻译论文
        
        Args:
            papers_by_category: 按类别分组的论文
            force_retranslate: 是否强制重新翻译
            
        Returns:
            成功翻译的论文数量
        """
        self.logger.info("开始翻译论文...")
        
        start_time = time.time()
        total_success = 0
        total_failed = 0
        
        try:
            for category, papers in papers_by_category.items():
                self.logger.info(f"翻译类别 {category} 的论文...")
                
                success, failed = self.translator.translate_papers_batch(papers, force_retranslate)
                total_success += success
                total_failed += failed
                
                self.logger.info(f"类别 {category} 翻译完成: 成功 {success}, 失败 {failed}")
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"论文翻译完成: 成功 {total_success}, 失败 {total_failed}, 耗时 {elapsed_time:.2f} 秒")
            
            return total_success
            
        except Exception as e:
            self.logger.error(f"翻译论文失败: {e}")
            return 0

    def send_daily_email(self, papers_by_category: Dict[str, List[PaperData]], 
                        recipients: Optional[List[str]] = None) -> bool:
        """
        发送每日邮件
        
        Args:
            papers_by_category: 按类别分组的论文
            recipients: 收件人列表
            
        Returns:
            是否发送成功
        """
        self.logger.info("开始发送每日邮件...")
        
        try:
            if not papers_by_category:
                self.logger.warning("没有论文数据，跳过邮件发送")
                return False
            
            success = self.email_sender.send_email(papers_by_category, recipients)
            
            if success:
                self.logger.info("每日邮件发送成功")
            else:
                self.logger.error("每日邮件发送失败")
            
            return success
            
        except Exception as e:
            self.logger.error(f"发送每日邮件失败: {e}")
            return False

    def run_daily_workflow(self, categories: Optional[List[str]] = None, 
                          force_retranslate: bool = False,
                          skip_translation: bool = False,
                          skip_email: bool = False) -> Dict[str, Any]:
        """
        运行完整的每日工作流程
        
        Args:
            categories: 要处理的类别列表
            force_retranslate: 是否强制重新翻译
            skip_translation: 是否跳过翻译步骤
            skip_email: 是否跳过邮件发送
            
        Returns:
            工作流程结果统计
        """
        self.logger.info("=" * 50)
        self.logger.info("开始运行每日工作流程")
        self.logger.info("=" * 50)
        
        start_time = time.time()
        results = {
            "start_time": datetime.now().isoformat(),
            "success": False,
            "papers_fetched": 0,
            "papers_translated": 0,
            "email_sent": False,
            "errors": []
        }
        
        try:
            # 步骤 1: 获取论文
            self.logger.info("步骤 1/3: 获取论文")
            papers_by_category = self.fetch_daily_papers(categories)
            
            total_papers = sum(len(papers) for papers in papers_by_category.values())
            if total_papers == 0:
                error_msg = "没有获取到任何论文"
                self.logger.error(error_msg)
                results["errors"].append(error_msg)
                return results
            results["papers_fetched"] = total_papers
            self.logger.info(f"共获取 {total_papers} 篇论文")
            
            # 步骤 2: 翻译论文
            if not skip_translation:
                self.logger.info("步骤 2/3: 翻译论文")
                translated_count = self.translate_papers(papers_by_category, force_retranslate)
                results["papers_translated"] = translated_count
                self.logger.info(f"共翻译 {translated_count} 篇论文")
            else:
                self.logger.info("步骤 2/3: 跳过翻译步骤")
            
            # 步骤 3: 发送邮件
            if not skip_email:
                self.logger.info("步骤 3/3: 发送邮件")
                email_success = self.send_daily_email(papers_by_category)
                results["email_sent"] = email_success
                
                if email_success:
                    self.logger.info("邮件发送成功")
                else:
                    error_msg = "邮件发送失败"
                    self.logger.error(error_msg)
                    results["errors"].append(error_msg)
            else:
                self.logger.info("步骤 3/3: 跳过邮件发送")
                results["email_sent"] = True  # 跳过时标记为成功
            
            # 清理旧数据
            try:
                self.storage.cleanup_old_data()
            except Exception as e:
                self.logger.warning(f"清理旧数据失败: {e}")
            
            results["success"] = True
            
        except Exception as e:
            error_msg = f"工作流程执行失败: {e}"
            self.logger.error(error_msg)
            results["errors"].append(error_msg)
        
        finally:
            elapsed_time = time.time() - start_time
            results["end_time"] = datetime.now().isoformat()
            results["elapsed_time"] = elapsed_time
            
            self.logger.info("=" * 50)
            self.logger.info(f"每日工作流程完成，耗时 {elapsed_time:.2f} 秒")
            self.logger.info(f"结果: {results}")
            self.logger.info("=" * 50)
        
        return results

    def preview_email(self, date: Optional[str] = None) -> str:
        """
        预览今日邮件内容
        
        Args:
            date: 日期字符串
            
        Returns:
            邮件内容预览
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        # 加载今日论文
        daily_data = self.storage.load_daily_papers(date)
        
        if not daily_data:
            return f"没有找到 {date} 的论文数据"
        
        # 重构数据格式
        papers_by_category = {}
        for category, paper_dicts in daily_data.get("papers_by_category", {}).items():
            papers_by_category[category] = [PaperData.from_dict(p) for p in paper_dicts]
        
        return self.email_sender.preview_email(papers_by_category, date)

    def get_system_status(self) -> Dict[str, Any]:
        """
        获取系统状态
        
        Returns:
            系统状态信息
        """
        return {
            "config": {
                "categories": self.config.arxiv.categories,
                "max_results_per_category": self.config.arxiv.max_results_per_category,
                "gpt_model": self.config.gpt.model,
                "email_recipients_count": len(self.config.email.recipients)
            },
            "storage": self.storage.get_statistics(),
            "connections": self.test_all_connections(),
            "last_check": datetime.now().isoformat()
        }

    def send_test_email(self) -> bool:
        """
        发送测试邮件
        
        Returns:
            是否发送成功
        """
        return self.email_sender.send_test_email()


def main():
    """主函数入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="arXiv Reader - 自动获取、翻译并推送 arXiv 论文")
    parser.add_argument("--config", default="config/config.yaml", help="配置文件路径")
    parser.add_argument("--test", action="store_true", help="测试连接")
    parser.add_argument("--test-email", action="store_true", help="发送测试邮件")
    parser.add_argument("--preview", action="store_true", help="预览今日邮件")
    parser.add_argument("--status", action="store_true", help="显示系统状态")
    parser.add_argument("--force-retranslate", action="store_true", help="强制重新翻译")
    parser.add_argument("--skip-translation", action="store_true", help="跳过翻译步骤")
    parser.add_argument("--skip-email", action="store_true", help="跳过邮件发送")
    parser.add_argument("--categories", nargs="+", help="指定类别列表")
    
    args = parser.parse_args()
    
    try:
        # 初始化 arXiv Reader
        reader = ArxivReader(args.config)
        
        if args.test:
            # 测试连接
            connections = reader.test_all_connections()
            print("连接测试结果:")
            for service, status in connections.items():
                status_text = "✅ 成功" if status else "❌ 失败"
                print(f"  {service}: {status_text}")
        
        elif args.test_email:
            # 发送测试邮件
            success = reader.send_test_email()
            if success:
                print("✅ 测试邮件发送成功")
            else:
                print("❌ 测试邮件发送失败")
        
        elif args.preview:
            # 预览邮件
            content = reader.preview_email()
            print("邮件内容预览:")
            print("-" * 50)
            print(content)
        
        elif args.status:
            # 显示系统状态
            status = reader.get_system_status()
            print("系统状态:")
            print(f"  配置的类别: {status['config']['categories']}")
            print(f"  每类别最大论文数: {status['config']['max_results_per_category']}")
            print(f"  GPT 模型: {status['config']['gpt_model']}")
            print(f"  邮件收件人数量: {status['config']['email_recipients_count']}")
            print(f"  存储的论文总数: {status['storage']['total_papers']}")
            print(f"  存储大小: {status['storage']['total_size_mb']} MB")
        
        else:
            # 运行每日工作流程
            results = reader.run_daily_workflow(
                categories=args.categories,
                force_retranslate=args.force_retranslate,
                skip_translation=args.skip_translation,
                skip_email=args.skip_email
            )
            
            if results["success"]:
                print("✅ 每日工作流程执行成功")
                print(f"  获取论文: {results['papers_fetched']} 篇")
                print(f"  翻译论文: {results['papers_translated']} 篇")
                print(f"  邮件发送: {'成功' if results['email_sent'] else '失败'}")
                print(f"  耗时: {results['elapsed_time']:.2f} 秒")
            else:
                print("❌ 每日工作流程执行失败")
                for error in results["errors"]:
                    print(f"  错误: {error}")
                sys.exit(1)
    
    except Exception as e:
        print(f"❌ 程序执行失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()