"""
线程池管理器
用于管理SSH采集任务的多线程执行
"""
import time
import threading
from concurrent.futures import ThreadPoolExecutor, Future, as_completed
from typing import Dict, Any, List, Optional, Callable
from .utils import logger
from .config import settings


class ThreadPoolManager:
    """线程池管理器"""
    
    def __init__(self, max_workers: Optional[int] = None):
        """
        初始化线程池管理器
        
        Args:
            max_workers: 最大工作线程数，默认从配置读取
        """
        self.max_workers = max_workers or settings.max_concurrent_threads
        self.timeout = settings.thread_pool_timeout
        self.enabled = settings.enable_threading
        
        self._executor: Optional[ThreadPoolExecutor] = None
        self._lock = threading.Lock()
        self._active_tasks: Dict[str, Future] = {}
        
        logger.info(f"线程池管理器初始化 - 最大线程数: {self.max_workers}, 超时时间: {self.timeout}s, 启用状态: {self.enabled}")
    
    def start(self):
        """启动线程池"""
        with self._lock:
            if self._executor is None and self.enabled:
                self._executor = ThreadPoolExecutor(
                    max_workers=self.max_workers,
                    thread_name_prefix="ssh-collector"
                )
                logger.info(f"线程池已启动，最大工作线程数: {self.max_workers}")
    
    def stop(self):
        """停止线程池"""
        with self._lock:
            if self._executor is not None:
                logger.info("正在停止线程池...")
                
                # 取消所有活跃任务
                for task_id, future in self._active_tasks.items():
                    if not future.done():
                        future.cancel()
                        logger.info(f"已取消任务: {task_id}")
                
                # 关闭线程池
                self._executor.shutdown(wait=True)
                self._executor = None
                self._active_tasks.clear()
                logger.info("线程池已停止")
    
    def submit_task(self, task_id: str, func: Callable, *args, **kwargs) -> Optional[Future]:
        """
        提交任务到线程池
        
        Args:
            task_id: 任务ID
            func: 要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            Future对象，如果未启用多线程则返回None
        """
        if not self.enabled:
            logger.debug(f"多线程未启用，直接执行任务: {task_id}")
            return None
        
        with self._lock:
            if self._executor is None:
                self.start()
            
            if self._executor is not None:
                future = self._executor.submit(func, *args, **kwargs)
                self._active_tasks[task_id] = future
                logger.debug(f"任务已提交到线程池: {task_id}")
                return future
            else:
                logger.warning(f"线程池未启动，无法提交任务: {task_id}")
                return None
    
    def execute_tasks_parallel(self, tasks: List[Dict[str, Any]], 
                             task_func: Callable, 
                             max_workers: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        并行执行多个任务
        
        Args:
            tasks: 任务列表，每个任务包含task_id和其他参数
            task_func: 执行任务的函数
            max_workers: 最大并发数，默认使用配置值
            
        Returns:
            任务执行结果列表
        """
        if not self.enabled or len(tasks) <= 1:
            # 如果未启用多线程或任务数量<=1，串行执行
            logger.info(f"串行执行 {len(tasks)} 个任务")
            results = []
            for task in tasks:
                try:
                    result = task_func(task)
                    results.append(result)
                except Exception as e:
                    logger.error(f"任务执行失败: {task.get('task_id', 'unknown')}, 错误: {e}")
                    results.append({
                        "task_id": task.get('task_id', 'unknown'),
                        "success": False,
                        "error": str(e),
                        "execution_time": 0
                    })
            return results
        
        # 并行执行
        workers = min(max_workers or self.max_workers, len(tasks))
        logger.info(f"并行执行 {len(tasks)} 个任务，使用 {workers} 个线程")
        
        results = []
        with ThreadPoolExecutor(max_workers=workers) as executor:
            # 提交所有任务
            future_to_task = {
                executor.submit(task_func, task): task 
                for task in tasks
            }
            
            # 收集结果
            for future in as_completed(future_to_task, timeout=self.timeout):
                task = future_to_task[future]
                task_id = task.get('task_id', 'unknown')
                
                try:
                    result = future.result()
                    results.append(result)
                    logger.debug(f"任务完成: {task_id}")
                except Exception as e:
                    logger.error(f"任务执行失败: {task_id}, 错误: {e}")
                    results.append({
                        "task_id": task_id,
                        "success": False,
                        "error": str(e),
                        "execution_time": 0
                    })
        
        return results
    
    def wait_for_task(self, task_id: str, timeout: Optional[float] = None) -> Any:
        """
        等待指定任务完成
        
        Args:
            task_id: 任务ID
            timeout: 超时时间，默认使用配置值
            
        Returns:
            任务执行结果
        """
        future = self._active_tasks.get(task_id)
        if future is None:
            raise ValueError(f"任务不存在: {task_id}")
        
        try:
            result = future.result(timeout=timeout or self.timeout)
            # 清理已完成的任务
            with self._lock:
                self._active_tasks.pop(task_id, None)
            return result
        except Exception as e:
            logger.error(f"等待任务完成失败: {task_id}, 错误: {e}")
            raise
    
    def cancel_task(self, task_id: str) -> bool:
        """
        取消指定任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            是否成功取消
        """
        future = self._active_tasks.get(task_id)
        if future is None:
            return False
        
        cancelled = future.cancel()
        if cancelled:
            with self._lock:
                self._active_tasks.pop(task_id, None)
            logger.info(f"任务已取消: {task_id}")
        
        return cancelled
    
    def get_active_task_count(self) -> int:
        """获取活跃任务数量"""
        with self._lock:
            return len([f for f in self._active_tasks.values() if not f.done()])
    
    def get_status(self) -> Dict[str, Any]:
        """获取线程池状态"""
        with self._lock:
            active_count = len([f for f in self._active_tasks.values() if not f.done()])
            return {
                "enabled": self.enabled,
                "max_workers": self.max_workers,
                "timeout": self.timeout,
                "active_tasks": active_count,
                "total_tasks": len(self._active_tasks),
                "executor_running": self._executor is not None
            }


# 全局线程池管理器实例
thread_pool_manager = ThreadPoolManager()