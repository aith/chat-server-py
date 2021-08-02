#!/usr/bin/env python3.8

import signal
import sys
import os
import re
import time
import asyncio
import socket
import collections
from asyncio import AbstractEventLoop

DEFAULT_PORT = 1234
MESSAGE_MAX = 20002
MESSAGE_CHUNK = 1024

class Server:
    rooms = collections.defaultdict(list)
    tasks = collections.defaultdict(list)  # per user

    def __init__(self, host, port):
        asyncio.run(self.main(host, port))

    async def echo(self, connection: socket, loop: AbstractEventLoop) -> None:
        while data := await loop.sock_recv(connection, 1024):
            await loop.sock_sendall(connection, data)

    async def get_commands(self, connection: socket, loop: AbstractEventLoop) -> None:
        byts = b''
        while chunk := await loop.sock_recv(connection, 1024):
            byts += chunk
            try:
                if self.is_oob(byts):
                    raise ValueError
                if self.is_eol(byts):
                    text = str(byts[:-2], encoding='utf8')
                    cmd, room, user = re.split('\s+|\n+', text)
                    self.do_commands(connection, loop, cmd, room, user)
            except ValueError:
                asyncio.create_task(self.send_msg(connection, loop, f"ERROR\n"))
                connection.close()
                return

    def do_commands(self, connection: socket, loop: AbstractEventLoop, cmd, room, user):
        if cmd.upper() == 'JOIN' and self.is_valid_name(room) and self.is_valid_name(user):
            asyncio.create_task(self.send_msg(connection, loop, f"You're going to room {room} as {user}\n"))
            asyncio.create_task(self.handle_chat(connection, loop, cmd, room, user))
        else:
            raise ValueError


    async def handle_chat(self, connection: socket, loop: AbstractEventLoop, cmd, room, user) -> None:
        # join
        for user_socket in self.rooms[room]:
            await loop.sock_sendall(user_socket, bytes(f'{user} has joined\n', encoding='utf8'))
        self.rooms[room].append(connection)
        msg = b''
        while chunk := await loop.sock_recv(connection, 1024):
            msg += chunk
            if self.is_eol(msg):
                # broadcast str
                msg = bytes(f"{user}: ", encoding='utf8') + msg
                for user_socket in self.rooms[room]:
                    await loop.sock_sendall(user_socket, msg)
            msg = b''

    def is_valid_name(self, st: str):
        # check is ascii and no non-printables
        return re.match('^[\x21-\x7F]+$', st) is not None and len(st) >= 1 and len(st) <= 20

    def is_oob(self, byts):
        return len(byts) > MESSAGE_MAX

    def is_eol(self, byts):
        return byts[-2:] == b'\r\n'


    async def listen_for_connection(self, server_socket: socket, loop: AbstractEventLoop):
        # for signame in {'SIGINT', 'SIGTERM'}:
        #     loop.add_signal_handler(getattr(signal, signame), shutdown)

        while True:
            connection, address = await loop.sock_accept(server_socket)  # Stops until Event Loop gets a socket w data
            connection.setblocking(False)
            print(f"Got a connection from {address}")
            asyncio.create_task(self.send_msg(connection, loop, "Format: JOIN {ROOMNAME} {USERNAME}\n"))
            asyncio.create_task(self.get_commands(connection, loop))

    async def send_msg(self, connection: socket, loop: AbstractEventLoop, st: str):
        await loop.sock_sendall(connection, bytes(st, encoding='utf8'))

    async def main(self, host, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_address = (host, port)
        # server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # allow the port be to reused
        server_socket.setblocking(False)
        server_socket.bind(server_address)
        server_socket.listen()
        await self.listen_for_connection(server_socket, asyncio.get_event_loop())


if __name__ == '__main__':
    port = 0
    host = 0
    try:
        host = int(sys.argv[1])
        port = int(sys.argv[2])
        if port < 0 or port > 65535:
            print("Error: invalid port number")
            sys.exit(1)
    except:
        port = DEFAULT_PORT
        host = 'localhost'
    n = os.fork()
    if True:
        if n > 0:  # SHADOW
            print(f"PARENT {os.getpid()} is waiting for {n}")
            try:
                (pid, status) = os.waitpid(n, 0)
                n = os.fork()  # Try again
            except OSError:  # Irrecoverable error
                print("Could not fork server head. Restarting.")
            except KeyboardInterrupt:  # Irrecoverable error
                print("Fully exiting.")
                exit(0)
        else:  # MAIN SERVER PROCESS
            try:
                s = Server(host, port)
            except ConnectionError:  # some unrecoverable error or segfault, so restart the server
                exit(1)
