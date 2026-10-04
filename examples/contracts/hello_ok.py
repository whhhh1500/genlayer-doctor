# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
from genlayer import *


class HelloGenLayer(gl.Contract):
    """Minimal intelligent contract: stores a greeting and counts updates."""

    greeting: str
    owner: Address
    updates: u256

    def __init__(self, greeting: str):
        self.greeting = greeting
        self.owner = gl.message.sender_address
        self.updates = u256(0)

    @gl.public.view
    def get_greeting(self) -> str:
        return self.greeting

    @gl.public.view
    def get_updates(self) -> int:
        return self.updates

    @gl.public.view
    def get_owner(self) -> str:
        return self.owner.as_hex

    @gl.public.write
    def set_greeting(self, new_greeting: str) -> None:
        self.greeting = new_greeting
        self.updates += u256(1)
