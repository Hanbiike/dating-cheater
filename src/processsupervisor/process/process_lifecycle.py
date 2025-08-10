"""
Process Lifecycle Manager - Enhanced State Machine Implementation

Система для управления жизненным циклом bot processes с расширенной
state machine, transition handling, lifecycle hooks и automated recovery.

Функции:
- Advanced process state machine с custom states
- Lifecycle hooks и event handlers
- State transition validation и logging
- Automated recovery mechanisms
- Process health checks и diagnostics
- Graceful shutdown coordination
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, Optional, List, Callable, Any, Set, Tuple
from collections import defaultdict, deque
import signal
import os


class ProcessState(Enum):
    """Состояния процесса"""
    INITIALIZING = auto()    # Инициализация
    STARTING = auto()        # Запуск
    RUNNING = auto()         # Работает
    PAUSING = auto()         # Приостановка
    PAUSED = auto()          # Приостановлен
    RESUMING = auto()        # Возобновление
    STOPPING = auto()        # Остановка
    STOPPED = auto()         # Остановлен
    RESTARTING = auto()      # Перезапуск
    FAILED = auto()          # Ошибка
    RECOVERING = auto()      # Восстановление
    TERMINATED = auto()      # Завершен
    UNKNOWN = auto()         # Неизвестно


class LifecycleEvent(Enum):
    """События жизненного цикла"""
    BEFORE_START = "before_start"
    AFTER_START = "after_start"
    BEFORE_STOP = "before_stop"
    AFTER_STOP = "after_stop"
    BEFORE_PAUSE = "before_pause"
    AFTER_PAUSE = "after_pause"
    BEFORE_RESUME = "before_resume"
    AFTER_RESUME = "after_resume"
    BEFORE_RESTART = "before_restart"
    AFTER_RESTART = "after_restart"
    ON_FAILURE = "on_failure"
    ON_RECOVERY = "on_recovery"
    ON_HEALTH_CHECK = "on_health_check"
    ON_STATE_CHANGE = "on_state_change"


class TransitionTrigger(Enum):
    """Триггеры переходов состояний"""
    MANUAL = "manual"           # Ручное управление
    AUTOMATIC = "automatic"     # Автоматическое
    HEALTH_CHECK = "health_check" # По результатам health check
    TIMEOUT = "timeout"         # По таймауту
    ERROR = "error"            # По ошибке
    SIGNAL = "signal"          # По системному сигналу
    EXTERNAL = "external"      # Внешнее воздействие


@dataclass
class StateTransition:
    """Переход состояния"""
    transition_id: str
    process_id: str
    from_state: ProcessState
    to_state: ProcessState
    trigger: TransitionTrigger
    timestamp: float
    duration: Optional[float] = None
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class LifecycleHook:
    """Хук жизненного цикла"""
    hook_id: str
    event: LifecycleEvent
    handler: Callable
    priority: int = 0
    enabled: bool = True
    description: str = ""
    
    def __hash__(self):
        return hash(self.hook_id)


@dataclass
class ProcessHealthInfo:
    """Информация о здоровье процесса"""
    process_id: str
    is_healthy: bool
    last_check: float
    response_time: float = 0.0
    error_count: int = 0
    last_error: Optional[str] = None
    health_score: float = 1.0
    checks_performed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def update_health(self, healthy: bool, response_time: float = 0.0, error: Optional[str] = None):
        """Обновление информации о здоровье"""
        self.is_healthy = healthy
        self.last_check = time.time()
        self.response_time = response_time
        self.checks_performed += 1
        
        if not healthy:
            self.error_count += 1
            self.last_error = error
            # Снижение health score
            self.health_score = max(0.0, self.health_score - 0.1)
        else:
            # Постепенное восстановление health score
            self.health_score = min(1.0, self.health_score + 0.05)


class StateTransitionValidator:
    """Валидатор переходов состояний"""
    
    def __init__(self):
        # Определение допустимых переходов
        self.valid_transitions = {
            ProcessState.INITIALIZING: {ProcessState.STARTING, ProcessState.FAILED},
            ProcessState.STARTING: {ProcessState.RUNNING, ProcessState.FAILED},
            ProcessState.RUNNING: {ProcessState.PAUSING, ProcessState.STOPPING, ProcessState.RESTARTING, ProcessState.FAILED},
            ProcessState.PAUSING: {ProcessState.PAUSED, ProcessState.RUNNING, ProcessState.FAILED},
            ProcessState.PAUSED: {ProcessState.RESUMING, ProcessState.STOPPING, ProcessState.FAILED},
            ProcessState.RESUMING: {ProcessState.RUNNING, ProcessState.FAILED},
            ProcessState.STOPPING: {ProcessState.STOPPED, ProcessState.FAILED},
            ProcessState.STOPPED: {ProcessState.STARTING, ProcessState.TERMINATED},
            ProcessState.RESTARTING: {ProcessState.STOPPING, ProcessState.STARTING, ProcessState.FAILED},
            ProcessState.FAILED: {ProcessState.RECOVERING, ProcessState.STOPPING, ProcessState.TERMINATED},
            ProcessState.RECOVERING: {ProcessState.STARTING, ProcessState.FAILED},
            ProcessState.TERMINATED: set(),  # Финальное состояние
            ProcessState.UNKNOWN: {ProcessState.STARTING, ProcessState.FAILED, ProcessState.TERMINATED}
        }
    
    def is_valid_transition(self, from_state: ProcessState, to_state: ProcessState) -> bool:
        """Проверка валидности перехода"""
        return to_state in self.valid_transitions.get(from_state, set())
    
    def get_possible_transitions(self, from_state: ProcessState) -> Set[ProcessState]:
        """Получение возможных переходов из состояния"""
        return self.valid_transitions.get(from_state, set())


class ProcessLifecycleManager:
    """
    Process Lifecycle Manager - система управления жизненным циклом процессов
    
    Функции:
    - Advanced state machine для bot processes
    - Lifecycle hooks и event handling
    - State transition validation и logging
    - Automated recovery mechanisms
    - Health monitoring и diagnostics
    """
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        
        # State management
        self.process_states: Dict[str, ProcessState] = {}
        self.state_transitions: Dict[str, List[StateTransition]] = defaultdict(list)
        self.transition_validator = StateTransitionValidator()
        
        # Lifecycle hooks
        self.lifecycle_hooks: Dict[LifecycleEvent, List[LifecycleHook]] = defaultdict(list)
        
        # Health monitoring
        self.health_info: Dict[str, ProcessHealthInfo] = {}
        self.health_check_enabled = True
        self.health_check_interval = 30.0  # 30 секунд
        
        # Recovery configuration
        self.recovery_enabled = True
        self.max_recovery_attempts = 3
        self.recovery_backoff = [1, 5, 15]  # Секунды между попытками
        self.recovery_attempts: Dict[str, int] = defaultdict(int)
        
        # Async tasks
        self.monitoring_tasks: List[asyncio.Task] = []
        self.is_running = False
        
        # Statistics
        self.stats = {
            'total_transitions': 0,
            'failed_transitions': 0,
            'recovery_attempts': 0,
            'successful_recoveries': 0,
            'health_checks_performed': 0,
            'hooks_executed': 0
        }
        
        # Timeouts для состояний
        self.state_timeouts = {
            ProcessState.INITIALIZING: 60.0,  # 1 минута
            ProcessState.STARTING: 120.0,     # 2 минуты
            ProcessState.STOPPING: 60.0,      # 1 минута
            ProcessState.PAUSING: 30.0,       # 30 секунд
            ProcessState.RESUMING: 30.0,      # 30 секунд
            ProcessState.RESTARTING: 180.0,   # 3 минуты
            ProcessState.RECOVERING: 300.0    # 5 минут
        }
        
        # Timeout tracking
        self.state_start_times: Dict[str, float] = {}
    
    async def start(self):
        """Запуск Lifecycle Manager"""
        try:
            self.logger.info("Starting Process Lifecycle Manager")
            
            self.is_running = True
            
            # Запуск мониторинга
            if self.health_check_enabled:
                self.monitoring_tasks.append(
                    asyncio.create_task(self._health_monitoring_loop())
                )
            
            # Запуск проверки таймаутов
            self.monitoring_tasks.append(
                asyncio.create_task(self._timeout_monitoring_loop())
            )
            
            self.logger.info("Process Lifecycle Manager started")
            
        except Exception as e:
            self.logger.error(f"Error starting Process Lifecycle Manager: {e}")
            raise
    
    async def stop(self):
        """Остановка Lifecycle Manager"""
        try:
            self.logger.info("Stopping Process Lifecycle Manager")
            
            self.is_running = False
            
            # Остановка задач мониторинга
            for task in self.monitoring_tasks:
                task.cancel()
            
            if self.monitoring_tasks:
                await asyncio.gather(*self.monitoring_tasks, return_exceptions=True)
            
            self.monitoring_tasks.clear()
            
            self.logger.info("Process Lifecycle Manager stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping Process Lifecycle Manager: {e}")
    
    async def register_process(self, process_id: str, initial_state: ProcessState = ProcessState.INITIALIZING) -> bool:
        """Регистрация процесса в системе"""
        try:
            if process_id in self.process_states:
                self.logger.warning(f"Process {process_id} already registered")
                return False
            
            # Установка начального состояния
            self.process_states[process_id] = initial_state
            self.state_start_times[process_id] = time.time()
            
            # Инициализация health info
            self.health_info[process_id] = ProcessHealthInfo(
                process_id=process_id,
                is_healthy=True,
                last_check=time.time()
            )
            
            # Выполнение lifecycle hooks
            await self._execute_lifecycle_hooks(LifecycleEvent.ON_STATE_CHANGE, process_id, {
                'new_state': initial_state,
                'old_state': None
            })
            
            self.logger.info(f"Registered process {process_id} with state {initial_state.name}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error registering process {process_id}: {e}")
            return False
    
    async def unregister_process(self, process_id: str) -> bool:
        """Удаление процесса из системы"""
        try:
            if process_id not in self.process_states:
                return False
            
            # Удаление данных
            del self.process_states[process_id]
            if process_id in self.health_info:
                del self.health_info[process_id]
            if process_id in self.state_start_times:
                del self.state_start_times[process_id]
            if process_id in self.recovery_attempts:
                del self.recovery_attempts[process_id]
            
            self.logger.info(f"Unregistered process {process_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"Error unregistering process {process_id}: {e}")
            return False
    
    async def transition_state(self, process_id: str, new_state: ProcessState, 
                             trigger: TransitionTrigger = TransitionTrigger.MANUAL,
                             metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Переход процесса в новое состояние"""
        try:
            if process_id not in self.process_states:
                self.logger.error(f"Process {process_id} not registered")
                return False
            
            old_state = self.process_states[process_id]
            
            # Проверка валидности перехода
            if not self.transition_validator.is_valid_transition(old_state, new_state):
                self.logger.error(f"Invalid transition for process {process_id}: {old_state.name} -> {new_state.name}")
                self.stats['failed_transitions'] += 1
                return False
            
            transition_start = time.time()
            
            # Создание записи о переходе
            transition = StateTransition(
                transition_id=str(uuid.uuid4()),
                process_id=process_id,
                from_state=old_state,
                to_state=new_state,
                trigger=trigger,
                timestamp=transition_start,
                metadata=metadata or {}
            )
            
            try:
                # Выполнение pre-transition hooks
                await self._execute_state_specific_hooks(process_id, old_state, new_state, before=True)
                
                # Обновление состояния
                self.process_states[process_id] = new_state
                self.state_start_times[process_id] = time.time()
                
                # Завершение перехода
                transition.duration = time.time() - transition_start
                transition.success = True
                
                # Сохранение перехода
                self.state_transitions[process_id].append(transition)
                
                # Выполнение post-transition hooks
                await self._execute_state_specific_hooks(process_id, old_state, new_state, before=False)
                
                # Общий hook изменения состояния
                await self._execute_lifecycle_hooks(LifecycleEvent.ON_STATE_CHANGE, process_id, {
                    'old_state': old_state,
                    'new_state': new_state,
                    'trigger': trigger,
                    'transition': transition
                })
                
                self.stats['total_transitions'] += 1
                
                self.logger.info(f"Process {process_id} transitioned: {old_state.name} -> {new_state.name} ({trigger.value})")
                
                return True
                
            except Exception as e:
                # Откат состояния при ошибке
                transition.success = False
                transition.error = str(e)
                transition.duration = time.time() - transition_start
                
                self.state_transitions[process_id].append(transition)
                self.stats['failed_transitions'] += 1
                
                self.logger.error(f"Error in state transition for process {process_id}: {e}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error transitioning state for process {process_id}: {e}")
            return False
    
    async def start_process(self, process_id: str) -> bool:
        """Запуск процесса"""
        current_state = self.get_process_state(process_id)
        
        if current_state in [ProcessState.INITIALIZING, ProcessState.STOPPED]:
            return await self.transition_state(process_id, ProcessState.STARTING, TransitionTrigger.MANUAL)
        elif current_state == ProcessState.STARTING:
            return await self.transition_state(process_id, ProcessState.RUNNING, TransitionTrigger.AUTOMATIC)
        
        return False
    
    async def stop_process(self, process_id: str, graceful: bool = True) -> bool:
        """Остановка процесса"""
        current_state = self.get_process_state(process_id)
        
        if current_state in [ProcessState.RUNNING, ProcessState.PAUSED]:
            return await self.transition_state(process_id, ProcessState.STOPPING, TransitionTrigger.MANUAL, {
                'graceful': graceful
            })
        elif current_state == ProcessState.STOPPING:
            return await self.transition_state(process_id, ProcessState.STOPPED, TransitionTrigger.AUTOMATIC)
        
        return False
    
    async def pause_process(self, process_id: str) -> bool:
        """Приостановка процесса"""
        current_state = self.get_process_state(process_id)
        
        if current_state == ProcessState.RUNNING:
            return await self.transition_state(process_id, ProcessState.PAUSING, TransitionTrigger.MANUAL)
        elif current_state == ProcessState.PAUSING:
            return await self.transition_state(process_id, ProcessState.PAUSED, TransitionTrigger.AUTOMATIC)
        
        return False
    
    async def resume_process(self, process_id: str) -> bool:
        """Возобновление процесса"""
        current_state = self.get_process_state(process_id)
        
        if current_state == ProcessState.PAUSED:
            return await self.transition_state(process_id, ProcessState.RESUMING, TransitionTrigger.MANUAL)
        elif current_state == ProcessState.RESUMING:
            return await self.transition_state(process_id, ProcessState.RUNNING, TransitionTrigger.AUTOMATIC)
        
        return False
    
    async def restart_process(self, process_id: str) -> bool:
        """Перезапуск процесса"""
        current_state = self.get_process_state(process_id)
        
        if current_state in [ProcessState.RUNNING, ProcessState.PAUSED, ProcessState.FAILED]:
            success = await self.transition_state(process_id, ProcessState.RESTARTING, TransitionTrigger.MANUAL)
            if success:
                # Автоматическая последовательность: stopping -> starting -> running
                await asyncio.sleep(1)  # Небольшая задержка
                await self.transition_state(process_id, ProcessState.STOPPING, TransitionTrigger.AUTOMATIC)
                await asyncio.sleep(2)  # Время на остановку
                await self.transition_state(process_id, ProcessState.STARTING, TransitionTrigger.AUTOMATIC)
                await asyncio.sleep(1)  # Время на запуск
                return await self.transition_state(process_id, ProcessState.RUNNING, TransitionTrigger.AUTOMATIC)
            
        return False
    
    async def mark_process_failed(self, process_id: str, error: str) -> bool:
        """Пометка процесса как неудачного"""
        success = await self.transition_state(process_id, ProcessState.FAILED, TransitionTrigger.ERROR, {
            'error': error
        })
        
        if success:
            await self._execute_lifecycle_hooks(LifecycleEvent.ON_FAILURE, process_id, {
                'error': error
            })
            
            # Автоматическое восстановление
            if self.recovery_enabled:
                await self._attempt_recovery(process_id)
        
        return success
    
    async def _attempt_recovery(self, process_id: str):
        """Попытка восстановления процесса"""
        try:
            attempts = self.recovery_attempts[process_id]
            
            if attempts >= self.max_recovery_attempts:
                self.logger.warning(f"Max recovery attempts reached for process {process_id}")
                return
            
            # Увеличение счетчика попыток
            self.recovery_attempts[process_id] += 1
            self.stats['recovery_attempts'] += 1
            
            # Задержка перед восстановлением
            if attempts < len(self.recovery_backoff):
                backoff_time = self.recovery_backoff[attempts]
            else:
                backoff_time = self.recovery_backoff[-1]
            
            self.logger.info(f"Attempting recovery for process {process_id} (attempt {attempts + 1}/{self.max_recovery_attempts}) in {backoff_time}s")
            
            await asyncio.sleep(backoff_time)
            
            # Переход в состояние восстановления
            await self.transition_state(process_id, ProcessState.RECOVERING, TransitionTrigger.AUTOMATIC)
            
            # Попытка запуска
            await asyncio.sleep(2)
            success = await self.transition_state(process_id, ProcessState.STARTING, TransitionTrigger.AUTOMATIC)
            
            if success:
                await asyncio.sleep(3)
                success = await self.transition_state(process_id, ProcessState.RUNNING, TransitionTrigger.AUTOMATIC)
                
                if success:
                    # Успешное восстановление
                    self.recovery_attempts[process_id] = 0  # Сброс счетчика
                    self.stats['successful_recoveries'] += 1
                    
                    await self._execute_lifecycle_hooks(LifecycleEvent.ON_RECOVERY, process_id, {
                        'recovery_attempt': attempts + 1
                    })
                    
                    self.logger.info(f"Successfully recovered process {process_id}")
                else:
                    # Неудачное восстановление
                    await self.mark_process_failed(process_id, "Recovery failed - could not start")
            else:
                await self.mark_process_failed(process_id, "Recovery failed - could not transition to starting")
                
        except Exception as e:
            self.logger.error(f"Error during recovery for process {process_id}: {e}")
            await self.mark_process_failed(process_id, f"Recovery error: {e}")
    
    def get_process_state(self, process_id: str) -> Optional[ProcessState]:
        """Получение текущего состояния процесса"""
        return self.process_states.get(process_id)
    
    def get_process_health(self, process_id: str) -> Optional[ProcessHealthInfo]:
        """Получение информации о здоровье процесса"""
        return self.health_info.get(process_id)
    
    async def perform_health_check(self, process_id: str, health_check_func: Optional[Callable] = None) -> bool:
        """Выполнение проверки здоровья процесса"""
        try:
            if process_id not in self.health_info:
                return False
            
            health_info = self.health_info[process_id]
            start_time = time.time()
            
            # Выполнение проверки
            if health_check_func:
                try:
                    is_healthy = await health_check_func(process_id)
                    error = None
                except Exception as e:
                    is_healthy = False
                    error = str(e)
            else:
                # Базовая проверка - процесс зарегистрирован и не в состоянии FAILED
                current_state = self.get_process_state(process_id)
                is_healthy = current_state not in [ProcessState.FAILED, ProcessState.TERMINATED, ProcessState.UNKNOWN]
                error = None if is_healthy else f"Process in unhealthy state: {current_state.name if current_state else 'None'}"
            
            response_time = time.time() - start_time
            
            # Обновление health info
            health_info.update_health(is_healthy, response_time, error)
            
            self.stats['health_checks_performed'] += 1
            
            # Выполнение hooks
            await self._execute_lifecycle_hooks(LifecycleEvent.ON_HEALTH_CHECK, process_id, {
                'is_healthy': is_healthy,
                'response_time': response_time,
                'error': error,
                'health_score': health_info.health_score
            })
            
            # Автоматическое действие при нездоровом состоянии
            if not is_healthy and self.get_process_state(process_id) == ProcessState.RUNNING:
                self.logger.warning(f"Health check failed for process {process_id}: {error}")
                
                # Если health score критически низкий, помечаем как failed
                if health_info.health_score < 0.2:
                    await self.mark_process_failed(process_id, f"Health check failed: {error}")
            
            return is_healthy
            
        except Exception as e:
            self.logger.error(f"Error performing health check for process {process_id}: {e}")
            return False
    
    def register_lifecycle_hook(self, event: LifecycleEvent, handler: Callable, 
                               priority: int = 0, description: str = "") -> str:
        """Регистрация lifecycle hook"""
        hook_id = str(uuid.uuid4())
        
        hook = LifecycleHook(
            hook_id=hook_id,
            event=event,
            handler=handler,
            priority=priority,
            description=description
        )
        
        self.lifecycle_hooks[event].append(hook)
        
        # Сортировка по приоритету (высокий приоритет первый)
        self.lifecycle_hooks[event].sort(key=lambda h: h.priority, reverse=True)
        
        self.logger.debug(f"Registered lifecycle hook {hook_id} for event {event.value}")
        
        return hook_id
    
    def unregister_lifecycle_hook(self, hook_id: str) -> bool:
        """Удаление lifecycle hook"""
        for event_hooks in self.lifecycle_hooks.values():
            for hook in event_hooks[:]:  # Копия для безопасного удаления
                if hook.hook_id == hook_id:
                    event_hooks.remove(hook)
                    self.logger.debug(f"Unregistered lifecycle hook {hook_id}")
                    return True
        
        return False
    
    async def _execute_lifecycle_hooks(self, event: LifecycleEvent, process_id: str, context: Dict[str, Any]):
        """Выполнение lifecycle hooks для события"""
        hooks = self.lifecycle_hooks.get(event, [])
        
        for hook in hooks:
            if not hook.enabled:
                continue
            
            try:
                if asyncio.iscoroutinefunction(hook.handler):
                    await hook.handler(process_id, context)
                else:
                    hook.handler(process_id, context)
                
                self.stats['hooks_executed'] += 1
                
            except Exception as e:
                self.logger.error(f"Error executing lifecycle hook {hook.hook_id} for event {event.value}: {e}")
    
    async def _execute_state_specific_hooks(self, process_id: str, old_state: ProcessState, 
                                          new_state: ProcessState, before: bool = True):
        """Выполнение hooks специфичных для переходов состояний"""
        # Мапинг состояний на события
        state_event_map = {
            ProcessState.STARTING: (LifecycleEvent.BEFORE_START, LifecycleEvent.AFTER_START),
            ProcessState.STOPPING: (LifecycleEvent.BEFORE_STOP, LifecycleEvent.AFTER_STOP),
            ProcessState.PAUSING: (LifecycleEvent.BEFORE_PAUSE, LifecycleEvent.AFTER_PAUSE),
            ProcessState.RESUMING: (LifecycleEvent.BEFORE_RESUME, LifecycleEvent.AFTER_RESUME),
            ProcessState.RESTARTING: (LifecycleEvent.BEFORE_RESTART, LifecycleEvent.AFTER_RESTART)
        }
        
        target_state = new_state if before else old_state
        
        if target_state in state_event_map:
            event = state_event_map[target_state][0 if before else 1]
            
            await self._execute_lifecycle_hooks(event, process_id, {
                'old_state': old_state,
                'new_state': new_state
            })
    
    async def _health_monitoring_loop(self):
        """Цикл мониторинга здоровья процессов"""
        while self.is_running:
            try:
                # Проверка всех зарегистрированных процессов
                for process_id in list(self.process_states.keys()):
                    current_state = self.get_process_state(process_id)
                    
                    # Проверяем только активные процессы
                    if current_state in [ProcessState.RUNNING, ProcessState.PAUSED]:
                        await self.perform_health_check(process_id)
                
                await asyncio.sleep(self.health_check_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in health monitoring loop: {e}")
                await asyncio.sleep(self.health_check_interval)
    
    async def _timeout_monitoring_loop(self):
        """Цикл мониторинга таймаутов состояний"""
        while self.is_running:
            try:
                current_time = time.time()
                
                for process_id, start_time in list(self.state_start_times.items()):
                    current_state = self.get_process_state(process_id)
                    
                    if current_state and current_state in self.state_timeouts:
                        timeout = self.state_timeouts[current_state]
                        
                        if current_time - start_time > timeout:
                            self.logger.warning(f"State timeout for process {process_id}: {current_state.name} ({timeout}s)")
                            
                            # Автоматическое действие при таймауте
                            if current_state in [ProcessState.STARTING, ProcessState.RECOVERING]:
                                await self.mark_process_failed(process_id, f"Timeout in state {current_state.name}")
                            elif current_state in [ProcessState.STOPPING, ProcessState.PAUSING]:
                                # Принудительная остановка
                                await self.transition_state(process_id, ProcessState.FAILED, TransitionTrigger.TIMEOUT)
                
                await asyncio.sleep(10)  # Проверка каждые 10 секунд
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in timeout monitoring loop: {e}")
                await asyncio.sleep(10)
    
    def get_process_statistics(self, process_id: str) -> Dict[str, Any]:
        """Получение статистики процесса"""
        if process_id not in self.process_states:
            return {}
        
        transitions = self.state_transitions.get(process_id, [])
        health_info = self.health_info.get(process_id)
        
        return {
            'current_state': self.process_states[process_id].name,
            'total_transitions': len(transitions),
            'failed_transitions': sum(1 for t in transitions if not t.success),
            'recovery_attempts': self.recovery_attempts.get(process_id, 0),
            'health_score': health_info.health_score if health_info else 0.0,
            'last_health_check': health_info.last_check if health_info else None,
            'uptime': time.time() - self.state_start_times.get(process_id, time.time()),
            'state_history': [
                {
                    'from_state': t.from_state.name,
                    'to_state': t.to_state.name,
                    'timestamp': t.timestamp,
                    'trigger': t.trigger.value,
                    'success': t.success
                } for t in transitions[-10:]  # Последние 10 переходов
            ]
        }
    
    def get_global_statistics(self) -> Dict[str, Any]:
        """Получение глобальной статистики"""
        total_processes = len(self.process_states)
        
        # Статистика по состояниям
        state_counts = defaultdict(int)
        for state in self.process_states.values():
            state_counts[state.name] += 1
        
        # Статистика по здоровью
        healthy_processes = sum(1 for h in self.health_info.values() if h.is_healthy)
        average_health_score = sum(h.health_score for h in self.health_info.values()) / max(1, len(self.health_info))
        
        return {
            'total_processes': total_processes,
            'healthy_processes': healthy_processes,
            'unhealthy_processes': total_processes - healthy_processes,
            'average_health_score': average_health_score,
            'state_distribution': dict(state_counts),
            'registered_hooks': sum(len(hooks) for hooks in self.lifecycle_hooks.values()),
            'performance_stats': self.stats.copy()
        }
