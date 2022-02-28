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
from random import randrange

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

from synapse.api.constants import (
    EventContentFields,
    EventTypes,
    HistoryVisibility,
    JoinRules,
    Membership,
    RoomTypes,
)

from typing import (
    Iterable,
    List,
    Mapping,
    Optional,
    Sequence,
    Tuple,
    Union,
    overload,
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
        self._room_summary_handler = self._homeserver.get_room_summary_handler()
        self._server_name  = self._homeserver.config.server.server_name
        self._store = self._homeserver.get_datastore()
        self._event_creation_handler = self._homeserver.get_event_creation_handler()

        self._allowed_events = [
            "m.booth.chat.disabled",
            "m.booth.chat.enabled",
            "m.booth.chat.deleted",
            "m.booth.retention",
        ]

        self._api.register_third_party_rules_callbacks(
            on_new_event=self.send_event_to_rooms,
        )

    async def is_room_a_space(self,event: EventBase):
        if "room_id" not in event :
            return False;
        room_id = event.room_id
        room_entry = await self._store.get_room_with_stats(room_id) 
        logger.info(room_entry.keys())
        logger.info(room_entry.values())
        if room_entry == None:
            return None

        current_state_ids = await self._store.get_current_state_ids(room_id)
        create_event = await self._store.get_event(
            current_state_ids[(EventTypes.Create, "")]
        )


        if create_event.content.get(EventContentFields.ROOM_TYPE) == RoomTypes.SPACE :
            return True
        return False


    async def send_event_to_rooms(self, event: EventBase, *args: Any) -> None :
        event_dict = event.get_dict()
        logger.info("AUTOSENDEVENT")
        logger.info(event_dict)
        is_space = await self.is_room_a_space(event)
        if(is_space == None) :
            return is_space

        if (event.is_state() 
            and event.type in self._allowed_events
        ):
            room_id = event.room_id
            logger.info("Event.type = %s,event.state_key=%s,event.room_id=%s",event.type,event.state_key,event.room_id)
            #room_id = "!amPfLyNnQCdeGbFgMm:matrix.local" #event.room_id
            requester = create_requester('@admin:'+self._server_name, "syt_YWRtaW4_LQSDuXTmsrLjeegTeohm_3MPJch")
            admin = UserID.from_string('@admin:'+self._server_name)
            admin_requester = create_requester(
                admin, authenticated_entity=requester.authenticated_entity
            )
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
                /**/
                if event.type == 'm.booth.retention' :
                    event.type = 'm.room.retention';
                    
                for room in rooms['rooms'] :
                    if 'room_type' in room and room['room_type'] == 'm.space':
                        continue

                    #is_in_room = await self._store.is_host_joined(room['room_id'], self._server_name )

                    logger.info("RoomiD = %s, roomName = %s",room['room_id'],room['name'])
                    l_room_id, l_remote_room_hosts = await self.resolve_room_id(room['room_id'])

                    content = event.content
                    content['xyz'] = randrange(1000000)
                    # wir müssen die Zeit hier aktualisieren, sonst wird es als selber event genommen
                    # wir nehmen hier die Millisekunden da time.time() uns den Wert als Floating Point zurückgibt
                    event_dict = {
                            "room_id": l_room_id,
                            "sender": event.sender,
                            "type": event.type,
                            "content": content,
                            "state_key": "",
                            "now" : int(time.time()*1000),
                            "precision" : time.time_ns() % 1000000
                    }
                    await self._event_creation_handler.create_and_send_nonmember_event(requester, event_dict,ratelimit=False)
            except Exception as e:
                logger.info(traceback.format_exc())
                return None;

        return None 

    async def resolve_room_id(
        self, room_identifier: str, remote_room_hosts: Optional[List[str]] = None
    ) -> Tuple[str, Optional[List[str]]]:
        """
        from synapse/rest/servlet.py
        Resolve a room identifier to a room ID, if necessary.

        This also performanes checks to ensure the room ID is of the proper form.

        Args:
            room_identifier: The room ID or alias.
            remote_room_hosts: The potential remote room hosts to use.

        Returns:
            The resolved room ID.

        Raises:
            SynapseError if the room ID is of the wrong form.
        """
        if RoomID.is_valid(room_identifier):
            resolved_room_id = room_identifier
        elif RoomAlias.is_valid(room_identifier):
            room_alias = RoomAlias.from_string(room_identifier)
            (
                room_id,
                remote_room_hosts,
            ) = await self._room_member_handler.lookup_room_alias(room_alias)
            resolved_room_id = room_id.to_string()
        else:
            raise Exception(
                400, "%s was not legal room ID or room alias" % (room_identifier,)
            )
        if not resolved_room_id:
            raise Exception(
                400, "Unknown room ID or room alias %s" % room_identifier
            )
        return resolved_room_id, remote_room_hosts

