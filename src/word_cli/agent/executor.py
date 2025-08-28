"""
Tool execution engine with transaction support.

This module handles the execution of tools with proper error handling,
validation, and transaction management for safe document operations.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import logging
import time

from .tools import DocumentTool, ToolExecutionResult
from ..core.document_model import DocumentModel
from ..version.version_control import VersionController, DocumentChange
from .sub_agents.validation_agent import ValidationAgent, ValidationLevel


class TransactionStatus(Enum):
    """Status of a transaction."""
    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclass
class ToolExecution:
    """Represents a single tool execution within a transaction."""
    
    execution_id: str
    tool: DocumentTool
    parameters: Dict[str, Any]
    status: TransactionStatus = TransactionStatus.PENDING
    result: Optional[ToolExecutionResult] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    error: Optional[str] = None
    
    @property
    def duration(self) -> Optional[float]:
        """Get execution duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


@dataclass
class Transaction:
    """Represents a transaction containing multiple tool executions."""
    
    transaction_id: str
    executions: List[ToolExecution] = field(default_factory=list)
    status: TransactionStatus = TransactionStatus.PENDING
    atomic: bool = True  # All-or-nothing execution
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    # Rollback information
    rollback_version: Optional[str] = None
    rollback_data: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_complete(self) -> bool:
        """Check if all executions are complete."""
        return all(exec.status == TransactionStatus.COMPLETED for exec in self.executions)
    
    @property
    def has_failures(self) -> bool:
        """Check if any executions failed."""
        return any(exec.status == TransactionStatus.FAILED for exec in self.executions)
    
    @property
    def total_duration(self) -> Optional[float]:
        """Get total transaction duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return None


class ToolExecutor:
    """
    Executes tools with proper validation, error handling, and transaction support.
    
    Provides safe execution of document tools with rollback capabilities
    and comprehensive validation.
    """
    
    def __init__(self, validation_level: ValidationLevel = ValidationLevel.NORMAL):
        self.validation_agent = ValidationAgent(validation_level)
        self.logger = logging.getLogger(__name__)
        
        # Active transactions
        self.active_transactions: Dict[str, Transaction] = {}
        
        # Execution statistics
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0
    
    async def execute_tool(
        self,
        tool: DocumentTool,
        parameters: Dict[str, Any],
        document: DocumentModel,
        version_controller: Optional[VersionController] = None,
        validate_before: bool = True,
        validate_after: bool = True
    ) -> ToolExecutionResult:
        """
        Execute a single tool with validation and error handling.
        
        Args:
            tool: Tool to execute
            parameters: Tool parameters
            document: Target document
            version_controller: Version controller for rollback
            validate_before: Validate before execution
            validate_after: Validate after execution
            
        Returns:
            Tool execution result
        """
        self.total_executions += 1
        execution_start = time.time()
        
        try:
            # Pre-execution validation
            if validate_before:
                pre_validation = self.validation_agent.validate_document(document)
                if not pre_validation.passed:
                    self.failed_executions += 1
                    return ToolExecutionResult(
                        success=False,
                        error=f"Pre-execution validation failed: {pre_validation.summary}",
                        data={'validation_issues': [issue.description for issue in pre_validation.critical_issues]}
                    )
            
            # Create backup point if version controller available
            backup_version = None
            if version_controller and tool.category.value in ['editing', 'structure']:
                backup_version = version_controller.commit(
                    document,
                    f"Backup before {tool.name}",
                    author="tool-executor-backup"
                )
            
            # Execute the tool
            self.logger.info(f"Executing tool {tool.name} with parameters: {parameters}")
            result = await tool.execute(parameters, document, version_controller)
            
            # Post-execution validation
            if result.success and validate_after and result.document_modified:
                post_validation = self.validation_agent.validate_document(document)
                
                if not post_validation.passed:
                    # Rollback if validation fails
                    if backup_version and version_controller:
                        rollback_doc = version_controller.rollback(backup_version.version_id)
                        if rollback_doc:
                            # Update the document reference
                            document.__dict__.update(rollback_doc.__dict__)
                    
                    self.failed_executions += 1
                    return ToolExecutionResult(
                        success=False,
                        error=f"Post-execution validation failed: {post_validation.summary}",
                        data={'validation_issues': [issue.description for issue in post_validation.critical_issues]}
                    )
            
            # Update statistics
            if result.success:
                self.successful_executions += 1
            else:
                self.failed_executions += 1
            
            # Add execution metadata
            execution_time = time.time() - execution_start
            result.data = result.data or {}
            result.data['execution_time'] = execution_time
            result.data['tool_name'] = tool.name
            
            return result
            
        except Exception as e:
            self.failed_executions += 1
            self.logger.error(f"Tool execution error: {e}", exc_info=True)
            
            return ToolExecutionResult(
                success=False,
                error=f"Tool execution failed: {str(e)}",
                data={'exception_type': type(e).__name__}
            )
    
    async def execute_transaction(
        self,
        transaction: Transaction,
        document: DocumentModel,
        version_controller: Optional[VersionController] = None
    ) -> Transaction:
        """
        Execute a transaction containing multiple tool operations.
        
        Args:
            transaction: Transaction to execute
            document: Target document
            version_controller: Version controller for rollback
            
        Returns:
            Updated transaction with results
        """
        transaction.start_time = time.time()
        transaction.status = TransactionStatus.EXECUTING
        
        # Create transaction backup
        if version_controller and transaction.atomic:
            backup_version = version_controller.commit(
                document,
                f"Backup before transaction {transaction.transaction_id}",
                author="transaction-backup"
            )
            transaction.rollback_version = backup_version.version_id
        
        try:
            # Execute all tools in the transaction
            for execution in transaction.executions:
                execution.start_time = time.time()
                execution.status = TransactionStatus.EXECUTING
                
                try:
                    # Execute the tool
                    result = await self.execute_tool(
                        execution.tool,
                        execution.parameters,
                        document,
                        version_controller,
                        validate_before=True,
                        validate_after=False  # Validate at transaction level
                    )
                    
                    execution.result = result
                    execution.end_time = time.time()
                    
                    if result.success:
                        execution.status = TransactionStatus.COMPLETED
                    else:
                        execution.status = TransactionStatus.FAILED
                        execution.error = result.error
                        
                        # If atomic transaction and this fails, stop here
                        if transaction.atomic:
                            break
                
                except Exception as e:
                    execution.status = TransactionStatus.FAILED
                    execution.error = str(e)
                    execution.end_time = time.time()
                    
                    if transaction.atomic:
                        break
            
            # Check transaction results
            if transaction.atomic and transaction.has_failures:
                # Rollback atomic transaction
                await self._rollback_transaction(transaction, document, version_controller)
                transaction.status = TransactionStatus.ROLLED_BACK
            
            elif transaction.is_complete:
                # All executions completed successfully
                transaction.status = TransactionStatus.COMPLETED
                
                # Final validation for atomic transactions
                if transaction.atomic:
                    final_validation = self.validation_agent.validate_document(document)
                    if not final_validation.passed:
                        await self._rollback_transaction(transaction, document, version_controller)
                        transaction.status = TransactionStatus.ROLLED_BACK
            
            else:
                # Some executions failed in non-atomic transaction
                transaction.status = TransactionStatus.FAILED
            
        except Exception as e:
            self.logger.error(f"Transaction execution error: {e}", exc_info=True)
            transaction.status = TransactionStatus.FAILED
            
            if transaction.atomic:
                await self._rollback_transaction(transaction, document, version_controller)
                transaction.status = TransactionStatus.ROLLED_BACK
        
        finally:
            transaction.end_time = time.time()
            
            # Remove from active transactions
            if transaction.transaction_id in self.active_transactions:
                del self.active_transactions[transaction.transaction_id]
        
        return transaction
    
    async def _rollback_transaction(
        self,
        transaction: Transaction,
        document: DocumentModel,
        version_controller: Optional[VersionController]
    ) -> None:
        """Rollback a transaction to its backup state."""
        if not transaction.rollback_version or not version_controller:
            self.logger.warning("Cannot rollback transaction: no backup version available")
            return
        
        try:
            rollback_doc = version_controller.rollback(transaction.rollback_version)
            if rollback_doc:
                # Update the document in-place
                document.__dict__.update(rollback_doc.__dict__)
                self.logger.info(f"Successfully rolled back transaction {transaction.transaction_id}")
            else:
                self.logger.error(f"Failed to rollback transaction {transaction.transaction_id}")
                
        except Exception as e:
            self.logger.error(f"Rollback error: {e}", exc_info=True)
    
    def create_transaction(
        self,
        transaction_id: str,
        tools_and_params: List[tuple],
        atomic: bool = True
    ) -> Transaction:
        """
        Create a new transaction.
        
        Args:
            transaction_id: Unique transaction ID
            tools_and_params: List of (tool, parameters) tuples
            atomic: Whether transaction should be atomic
            
        Returns:
            Created transaction
        """
        transaction = Transaction(
            transaction_id=transaction_id,
            atomic=atomic
        )
        
        # Create executions for each tool
        for i, (tool, parameters) in enumerate(tools_and_params):
            execution = ToolExecution(
                execution_id=f"{transaction_id}_exec_{i}",
                tool=tool,
                parameters=parameters
            )
            transaction.executions.append(execution)
        
        # Add to active transactions
        self.active_transactions[transaction_id] = transaction
        
        return transaction
    
    def get_execution_stats(self) -> Dict[str, Any]:
        """Get execution statistics."""
        success_rate = (self.successful_executions / max(1, self.total_executions)) * 100
        
        return {
            'total_executions': self.total_executions,
            'successful_executions': self.successful_executions,
            'failed_executions': self.failed_executions,
            'success_rate': round(success_rate, 2),
            'active_transactions': len(self.active_transactions)
        }
    
    async def execute_batch(
        self,
        tools_and_params: List[tuple],
        document: DocumentModel,
        version_controller: Optional[VersionController] = None,
        atomic: bool = True,
        max_parallel: int = 3
    ) -> List[ToolExecutionResult]:
        """
        Execute multiple tools in batch.
        
        Args:
            tools_and_params: List of (tool, parameters) tuples
            document: Target document
            version_controller: Version controller
            atomic: Whether to execute as atomic transaction
            max_parallel: Maximum parallel executions
            
        Returns:
            List of execution results
        """
        import uuid
        
        transaction_id = f"batch_{uuid.uuid4().hex[:8]}"
        transaction = self.create_transaction(transaction_id, tools_and_params, atomic)
        
        if atomic or max_parallel == 1:
            # Sequential execution for atomic transactions
            executed_transaction = await self.execute_transaction(
                transaction, document, version_controller
            )
            return [exec.result for exec in executed_transaction.executions if exec.result]
        
        else:
            # Parallel execution for non-atomic batch
            semaphore = asyncio.Semaphore(max_parallel)
            
            async def execute_with_semaphore(tool, params):
                async with semaphore:
                    return await self.execute_tool(tool, params, document, version_controller)
            
            # Execute in parallel
            tasks = [
                execute_with_semaphore(tool, params) 
                for tool, params in tools_and_params
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Convert exceptions to error results
            processed_results = []
            for result in results:
                if isinstance(result, Exception):
                    processed_results.append(ToolExecutionResult(
                        success=False,
                        error=str(result)
                    ))
                else:
                    processed_results.append(result)
            
            return processed_results
    
    def validate_tool_parameters(
        self, 
        tool: DocumentTool, 
        parameters: Dict[str, Any]
    ) -> Optional[str]:
        """
        Validate tool parameters before execution.
        
        Args:
            tool: Tool to validate parameters for
            parameters: Parameters to validate
            
        Returns:
            Error message if validation fails, None if valid
        """
        # Check required parameters
        if hasattr(tool, 'parameters'):
            required_params = set(tool.parameters.keys())
            provided_params = set(parameters.keys())
            
            missing_params = required_params - provided_params
            if missing_params:
                return f"Missing required parameters: {', '.join(missing_params)}"
        
        # Tool-specific validation could be added here
        
        return None  # Valid
    
    async def preview_tool_execution(
        self,
        tool: DocumentTool,
        parameters: Dict[str, Any],
        document: DocumentModel
    ) -> Dict[str, Any]:
        """
        Preview what a tool execution would do without actually executing it.
        
        Args:
            tool: Tool to preview
            parameters: Tool parameters
            document: Target document
            
        Returns:
            Preview information
        """
        preview = {
            'tool_name': tool.name,
            'tool_description': tool.description,
            'parameters': parameters,
            'estimated_impact': 'unknown',
            'validation_warnings': []
        }
        
        # Parameter validation
        param_error = self.validate_tool_parameters(tool, parameters)
        if param_error:
            preview['validation_warnings'].append(param_error)
        
        # Estimate impact based on tool category
        if tool.category.value == 'editing':
            preview['estimated_impact'] = 'modifies document content'
        elif tool.category.value == 'structure':
            preview['estimated_impact'] = 'changes document structure'
        elif tool.category.value in ['reading', 'navigation']:
            preview['estimated_impact'] = 'read-only operation'
        
        return preview