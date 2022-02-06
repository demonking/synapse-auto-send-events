# Copyright 2021 The Matrix.org Foundation C.I.C.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
from typing import Any, Dict

import time

from synapse.api.constants import EventTypes
from synapse.events import EventBase
from synapse.module_api import ModuleApi
from synapse.types import StateMap


from synapse.types import (
    create_requester,
    UserID,
    UserInfo,
    JsonDict,
    RoomAlias,
    RoomID,
)


import logging
logger = logging.getLogger(__name__)

import requests

import traceback

class AutoSendEvents:
    def __init__(self, config: dict, api: ModuleApi):
        self._api = api

        self._homeserver = api._hs 
        self._room_member_handler = self._homeserver.get_room_member_handler()
        self._server_name  = self._homeserver.config.server.server_name
        self._store = self._homeserver.get_datastore()

        self._api.register_third_party_rules_callbacks(
            check_event_allowed=self.check_event_allowed,
        )


    def get_event_information(self, event : EventBase): 
        values = dict()
        values['is_space'] = False
        values['room_id'] = event.room_id

        if "invite_room_state" not in event.unsigned:
            return values['is_space'],values['room_id']

        for entry in event.unsigned['invite_room_state']:
            logger.info(entry)
            if 'type' not in entry :
                continue
            if entry['type'] == 'm.room.create':
                    values['is_space'] = ('type' in entry['content'] and entry['content']['type'] == 'm.space')
        return values['is_space'],values['room_id']


    async def check_event_allowed(self, event: EventBase, state: StateMap[EventBase]):
        if event.is_state() and event.type == EventTypes.PowerLevels:

            is_space, room_id = self.get_event_information(event); 
            if is_space :
                room_id = event.room_id
                logger.info("Event.type = %s,event.state_key=%s,event.room_id=%s",event.type,event.state_key,event.room_id)
                #room_id = "!amPfLyNnQCdeGbFgMm:matrix.local" #event.room_id
                requester = create_requester('@admin:'+self._server_name, "syt_YWRtaW4_LQSDuXTmsrLjeegTeohm_3MPJch")
                admin = UserID.from_string('@admin:'+self._server_name)
                admin_requester = create_requester(
                    admin, authenticated_entity=requester.authenticated_entity
                )
                event_dict = event.get_dict()
                logger.info(event_dict)
                try:
                    # https://github.com/matrix-org/synapse/blob/develop/synapse/handlers/room_summary.py#L257
                    room_summary_handler =self._homeserver.get_room_summary_handler()
                    logger.info("Request hierarchy for room_id =%s",room_id)
                    rooms = await room_summary_handler.get_room_hierarchy(
                        admin_requester,
                        room_id,
                        suggested_only=False,
                        max_depth=1,
                        limit=None,
                    )
                    #wenn keine rooms da, dann falsche Zugriff oder es gibt keine, sollte aber nicht möglich sein!
                    if 'rooms' not in rooms:
                        logger.info('NO ROOMS')
                        return None

                    for room in rooms['rooms'] :
                        if 'room_type' in room and room['room_type'] == 'm.space':
                            continue

                        #is_in_room = await self._store.is_host_joined(room['room_id'], self._server_name )

                        logger.info("RoomiD = %s, roomName = %s",room['room_id'],room['name'])
                        l_room_id, l_remote_room_hosts = await self.resolve_room_id(room['room_id'])

                        content = event.content
                        # wir müssen die Zeit hier aktualisieren, sonst wird es als selber event genommen
                        # wir nehmen hier die Millisekunden da time.time() uns den Wert als Floating Point zurückgibt
                        content['now'] = int(time.time()*1000)
                        await self._api.create_and_send_event_into_room(
                            {
                                "room_id": event.room_id,
                                "sender": event.sender,
                                "type": event.type,
                                "content": content,
                                "state_key": "",
                            }
                        )
                except Exception as e:
                    logger.info(traceback.format_exc())
                    return None;

        return True, None
