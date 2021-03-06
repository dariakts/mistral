# Copyright 2015 - Mirantis, Inc.
# Copyright 2020 Nokia Software.
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

from mistral.db.v2 import api as db_api_v2
from mistral.lang import parser as spec_parser
from mistral import services
from mistral.services import actions


def create_workbook_v2(definition, namespace='', scope='private',
                       validate=True):
    wb_spec = spec_parser.get_workbook_spec_from_yaml(
        definition,
        validate=services.is_validation_enabled(validate)
    )

    wb_values = _get_workbook_values(
        wb_spec,
        definition,
        scope,
        namespace
    )

    with db_api_v2.transaction():
        wb_db = db_api_v2.create_workbook(wb_values)

        _on_workbook_update(wb_db, wb_spec, namespace)

    return wb_db


def update_workbook_v2(definition, namespace='', scope='private',
                       validate=True):
    wb_spec = spec_parser.get_workbook_spec_from_yaml(
        definition,
        validate=services.is_validation_enabled(validate)
    )

    values = _get_workbook_values(wb_spec, definition, scope, namespace)

    with db_api_v2.transaction():
        wb_db = db_api_v2.update_workbook(values['name'], values)

        _, db_wfs = _on_workbook_update(wb_db, wb_spec, namespace)

    return wb_db


def _on_workbook_update(wb_db, wb_spec, namespace=''):
    db_actions = _create_or_update_actions(
        wb_db, wb_spec.get_actions(),
        namespace=namespace
    )

    db_wfs = _create_or_update_workflows(
        wb_db,
        wb_spec.get_workflows(),
        namespace
    )

    return db_actions, db_wfs


def _create_or_update_actions(wb_db, actions_spec, namespace):
    db_actions = []

    if actions_spec:
        for action_spec in actions_spec:
            action_name = '%s.%s' % (wb_db.name, action_spec.get_name())

            input_list = actions.get_input_list(
                action_spec.to_dict().get('input', [])
            )
            values = {
                'name': action_name,
                'spec': action_spec.to_dict(),
                'tags': action_spec.get_tags(),
                'definition': _get_action_definition(wb_db, action_spec),
                'description': action_spec.get_description(),
                'is_system': False,
                'input': ', '.join(input_list) if input_list else None,
                'scope': wb_db.scope,
                'project_id': wb_db.project_id,
                'namespace': namespace
            }

            db_actions.append(
                db_api_v2.create_or_update_action_definition(
                    action_name,
                    values
                )
            )

    return db_actions


def _create_or_update_workflows(wb_db, workflows_spec, namespace):
    db_wfs = []

    if workflows_spec:
        for wf_spec in workflows_spec:
            wf_name = '%s.%s' % (wb_db.name, wf_spec.get_name())

            values = {
                'name': wf_name,
                'definition': _get_wf_definition(wb_db, wf_spec),
                'spec': wf_spec.to_dict(),
                'scope': wb_db.scope,
                'project_id': wb_db.project_id,
                'namespace': namespace,
                'tags': wf_spec.get_tags(),
                'is_system': False
            }

            db_wfs.append(
                db_api_v2.create_or_update_workflow_definition(wf_name, values)
            )

    return db_wfs


def _get_workbook_values(wb_spec, definition, scope, namespace=None):
    values = {
        'name': wb_spec.get_name(),
        'tags': wb_spec.get_tags(),
        'definition': definition,
        'spec': wb_spec.to_dict(),
        'scope': scope,
        'namespace': namespace,
        'is_system': False
    }

    return values


def _get_wf_definition(wb_db, wf_spec):
    wf_definition = spec_parser.get_workflow_definition(
        wb_db.definition,
        wf_spec.get_name()
    )

    return wf_definition


def _get_action_definition(wb_db, action_spec):
    action_definition = spec_parser.get_action_definition(
        wb_db.definition,
        action_spec.get_name()
    )

    return action_definition
