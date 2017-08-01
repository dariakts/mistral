# Copyright 2014 - Mirantis, Inc.
# Copyright 2015 - StackStorm, Inc.
# Copyright 2017 - Brocade Communications Systems, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License");
#    you may not use this file except in compliance with the License.
#    You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS,
#    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#    See the License for the specific language governing permissions and
#    limitations under the License.

from oslo_config import cfg
from osprofiler import profiler

from mistral import context as auth_ctx
from mistral.engine import base as eng
from mistral.event_engine import base as evt_eng
from mistral.executors import base as exe
from mistral.rpc import base


_ENGINE_CLIENT = None
_EXECUTOR_CLIENT = None
_EVENT_ENGINE_CLIENT = None


def cleanup():
    """Intended to be used by tests to recreate all RPC related objects."""

    global _ENGINE_CLIENT
    global _EXECUTOR_CLIENT
    global _EVENT_ENGINE_CLIENT

    _ENGINE_CLIENT = None
    _EXECUTOR_CLIENT = None
    _EVENT_ENGINE_CLIENT = None


def get_engine_client():
    global _ENGINE_CLIENT

    if not _ENGINE_CLIENT:
        _ENGINE_CLIENT = EngineClient(cfg.CONF.engine)

    return _ENGINE_CLIENT


def get_executor_client():
    global _EXECUTOR_CLIENT

    if not _EXECUTOR_CLIENT:
        _EXECUTOR_CLIENT = ExecutorClient(cfg.CONF.executor)

    return _EXECUTOR_CLIENT


def get_event_engine_client():
    global _EVENT_ENGINE_CLIENT

    if not _EVENT_ENGINE_CLIENT:
        _EVENT_ENGINE_CLIENT = EventEngineClient(cfg.CONF.event_engine)

    return _EVENT_ENGINE_CLIENT


class EngineClient(eng.Engine):
    """RPC Engine client."""

    def __init__(self, rpc_conf_dict):
        """Constructs an RPC client for engine.

        :param rpc_conf_dict: Dict containing RPC configuration.
        """
        self._client = base.get_rpc_client_driver()(rpc_conf_dict)

    @base.wrap_messaging_exception
    def start_workflow(self, wf_identifier, wf_namespace, wf_input=None,
                       description='', **params):
        """Starts workflow sending a request to engine over RPC.

        :return: Workflow execution.
        """
        return self._client.sync_call(
            auth_ctx.ctx(),
            'start_workflow',
            workflow_identifier=wf_identifier,
            workflow_namespace=wf_namespace,
            workflow_input=wf_input or {},
            description=description,
            params=params
        )

    @base.wrap_messaging_exception
    def start_action(self, action_name, action_input,
                     description=None, **params):
        """Starts action sending a request to engine over RPC.

        :return: Action execution.
        """
        return self._client.sync_call(
            auth_ctx.ctx(),
            'start_action',
            action_name=action_name,
            action_input=action_input or {},
            description=description,
            params=params
        )

    @base.wrap_messaging_exception
    @profiler.trace('engine-client-on-action-complete', hide_args=True)
    def on_action_complete(self, action_ex_id, result, wf_action=False,
                           async_=False):
        """Conveys action result to Mistral Engine.

        This method should be used by clients of Mistral Engine to update
        state of a action execution once action has executed. One of the
        clients of this method is Mistral REST API server that receives
        action result from the outside action handlers.

        Note: calling this method serves an event notifying Mistral that
        it possibly needs to move the workflow on, i.e. run other workflow
        tasks for which all dependencies are satisfied.

        :param action_ex_id: Action execution id.
        :param result: Action execution result.
        :param wf_action: If True it means that the given id points to
            a workflow execution rather than action execution. It happens
            when a nested workflow execution sends its result to a parent
            workflow.
        :param async: If True, run action in asynchronous mode (w/o waiting
            for completion).
        :return: Action(or workflow if wf_action=True) execution object.
        """

        call = self._client.async_call if async_ else self._client.sync_call

        return call(
            auth_ctx.ctx(),
            'on_action_complete',
            action_ex_id=action_ex_id,
            result=result,
            wf_action=wf_action
        )

    @base.wrap_messaging_exception
    def pause_workflow(self, wf_ex_id):
        """Stops the workflow with the given execution id.

        :param wf_ex_id: Workflow execution id.
        :return: Workflow execution.
        """

        return self._client.sync_call(
            auth_ctx.ctx(),
            'pause_workflow',
            execution_id=wf_ex_id
        )

    @base.wrap_messaging_exception
    def rerun_workflow(self, task_ex_id, reset=True, env=None):
        """Rerun the workflow.

        This method reruns workflow with the given execution id
        at the specific task execution id.

        :param task_ex_id: Task execution id.
        :param reset: If true, then reset task execution state and purge
            action execution for the task.
        :param env: Environment variables to update.
        :return: Workflow execution.
        """

        return self._client.sync_call(
            auth_ctx.ctx(),
            'rerun_workflow',
            task_ex_id=task_ex_id,
            reset=reset,
            env=env
        )

    @base.wrap_messaging_exception
    def resume_workflow(self, wf_ex_id, env=None):
        """Resumes the workflow with the given execution id.

        :param wf_ex_id: Workflow execution id.
        :param env: Environment variables to update.
        :return: Workflow execution.
        """

        return self._client.sync_call(
            auth_ctx.ctx(),
            'resume_workflow',
            wf_ex_id=wf_ex_id,
            env=env
        )

    @base.wrap_messaging_exception
    def stop_workflow(self, wf_ex_id, state, message=None):
        """Stops workflow execution with given status.

        Once stopped, the workflow is complete with SUCCESS or ERROR,
        and can not be resumed.

        :param wf_ex_id: Workflow execution id
        :param state: State assigned to the workflow: SUCCESS or ERROR
        :param message: Optional information string

        :return: Workflow execution, model.Execution
        """

        return self._client.sync_call(
            auth_ctx.ctx(),
            'stop_workflow',
            execution_id=wf_ex_id,
            state=state,
            message=message
        )

    @base.wrap_messaging_exception
    def rollback_workflow(self, wf_ex_id):
        """Rolls back the workflow with the given execution id.

        :param wf_ex_id: Workflow execution id.

        :return: Workflow execution.
        """

        return self._client.sync_call(
            auth_ctx.ctx(),
            'rollback_workflow',
            execution_id=wf_ex_id
        )


class ExecutorClient(exe.Executor):
    """RPC Executor client."""

    def __init__(self, rpc_conf_dict):
        """Constructs an RPC client for the Executor."""

        self.topic = cfg.CONF.executor.topic
        self._client = base.get_rpc_client_driver()(rpc_conf_dict)

    @profiler.trace('executor-client-run-action')
    def run_action(self, action_ex_id, action_cls_str, action_cls_attrs,
                   params, safe_rerun, redelivered=False,
                   target=None, async_=True):
        """Sends a request to run action to executor.

        :param action_ex_id: Action execution id.
        :param action_cls_str: Action class name.
        :param action_cls_attrs: Action class attributes.
        :param params: Action input parameters.
        :param safe_rerun: If true, action would be re-run if executor dies
            during execution.
        :param redelivered: Tells if given action was run before on another
            executor.
        :param target: Target (group of action executors).
        :param async_: If True, run action in asynchronous mode (w/o waiting
            for completion).
        :return: Action result.
        """

        rpc_kwargs = {
            'action_ex_id': action_ex_id,
            'action_cls_str': action_cls_str,
            'action_cls_attrs': action_cls_attrs,
            'params': params,
            'safe_rerun': safe_rerun
        }

        rpc_client_method = (self._client.async_call
                             if async_ else self._client.sync_call)

        return rpc_client_method(auth_ctx.ctx(), 'run_action', **rpc_kwargs)


class EventEngineClient(evt_eng.EventEngine):
    """RPC EventEngine client."""

    def __init__(self, rpc_conf_dict):
        """Constructs an RPC client for the EventEngine service."""
        self._client = base.get_rpc_client_driver()(rpc_conf_dict)

    def create_event_trigger(self, trigger, events):
        return self._client.sync_call(
            auth_ctx.ctx(),
            'create_event_trigger',
            trigger=trigger,
            events=events
        )

    def delete_event_trigger(self, trigger, events):
        return self._client.sync_call(
            auth_ctx.ctx(),
            'delete_event_trigger',
            trigger=trigger,
            events=events
        )

    def update_event_trigger(self, trigger):
        return self._client.sync_call(
            auth_ctx.ctx(),
            'update_event_trigger',
            trigger=trigger,
        )
