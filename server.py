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
import logging
from dataclasses import dataclass

DEFAULT_PORT = 1234
DEFAULT_HOST = '0.0.0.0'
NEWLINE = '\r'
MESSAGE_MAX = 20000
MESSAGE_CHUNK = 1024

class Server:
    # __init__defined by dataclass
    def __init__(self):
        self.rooms = collections.defaultdict(set)
        self.RoomType = collections.namedtuple('RoomType', ('connection', 'userid'))

    def is_valid_name(self, st: str):
        # The range from x21 to x7F is the hexa alphanumeric and printable symbol range
        return len(st) <= 20 and re.match('^[\x21-\x7F]+$', st) is not None and len(st) >= 1

    def is_oob(self, byts):
        return len(byts) > MESSAGE_MAX

    def is_eol(self, byts):
        return byts[-1:] == b'\n'

    def remove_newline(self, byts):
        return byts[:-1] if byts[-1] == NEWLINE else byts

    async def broadcast(self, connection: socket, loop: AbstractEventLoop, cmd, room, user, msg: bytes) -> None:
        for idx, user_info in enumerate(self.rooms[room]):
            user_sock, uid = user_info
            try:
                await loop.sock_sendall(user_sock, msg)
            except BrokenPipeError as e:  # attempted to send data to client who has left, so remove them and alert others
                print("Removing connection " + str(self.rooms[room].remove(idx)))
                loop.create_task(self.broadcast(connection, loop, cmd, room, user,
                                                   bytes(f'{uid} has left\n', encoding='utf8')))
        if not self.rooms[room]:  # room is now empty, so delete it
            del self.rooms[room]

    async def do_chat(self, connection: socket, loop: AbstractEventLoop, cmd, room, user) -> None:
        # join
        self.rooms[room].add(self.RoomType(connection, user))
        for user_info in self.rooms[room]:
            user_sock, uid = user_info
            await loop.sock_sendall(user_sock, bytes(f'{user} has joined\n', encoding='utf8'))
        msg = b''
        try:
            while chunk := await loop.sock_recv(connection, 1024):
                msg += chunk
                if self.is_oob(msg):
                    raise ValueError
                if self.is_eol(msg):
                    msg = bytes(f"{user}: ", encoding='utf8') + msg
                    loop.create_task(self.broadcast(connection, loop, cmd, room, user, msg))
                msg = b''
        except BrokenPipeError:  # This user has exited
            connection.close()


    def parse_cmd(self, connection: socket, loop: AbstractEventLoop, cmd, room, user):
        if cmd.upper() == 'JOIN' and self.is_valid_name(room) and self.is_valid_name(user):
            loop.create_task(self.do_chat(connection, loop, cmd, room, user))
        else:
            raise ValueError

    async def get_cmd(self, connection: socket, loop: AbstractEventLoop) -> None:
        byts = b''
        while chunk := await loop.sock_recv(connection, 1024):
            byts += chunk
            try:
                if self.is_oob(byts):
                    byts = b''
                    continue
                if self.is_eol(byts):
                    text = str(self.remove_newline(byts), encoding='utf8')
                    cmd, room, user = re.split('\s+|\n+', text)
                    self.parse_cmd(connection, loop, cmd, room, user)
            except ValueError:  # propagated from parse_cmd
                loop.create_task(self.send_msg(connection, loop, f"ERROR\n"))
                connection.close()
                return

    async def send_msg(self, connection: socket, loop: AbstractEventLoop, st: str):
        await loop.sock_sendall(connection, bytes(st, encoding='utf8'))

    async def listen(self, server_socket: socket, loop: AbstractEventLoop):
        while True:
            connection, address = await loop.sock_accept(server_socket)  # Stops until Event Loop gets a socket w data
            connection.setblocking(False)
            print(f"Got a connection from {address}")
            loop.create_task(self.send_msg(connection, loop, "Format: JOIN {ROOMNAME} {USERNAME}\n"))
            loop.create_task(self.get_cmd(connection, loop))

    async def start(self, host, port):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # allow the port be to reused
        server_socket.setblocking(False)
        server_socket.bind((host, port))
        server_socket.listen()
        await self.listen(server_socket, loop.get_event_loop())


if __name__ == '__main__':
    host = DEFAULT_HOST
    port = None
    try:
        port = int(sys.argv[0])
        if port < 0 or port > 65535:
            print("Error: invalid host or port number")
            sys.exit(1)
    except:
        port = DEFAULT_PORT
    forkid = os.fork()
    while True:
        if forkid > 0:  # SHADOW
            print(f"PARENT {os.getpid()} is waiting for {forkid}")
            try:
                (pid, status) = os.waitpid(forkid, 0)
                forkid = os.fork()  # Try again
            except OSError:  # Irrecoverable error
                print("Could not fork server head. Restarting.")
            except KeyboardInterrupt:
                print("Fully exiting.")
                exit(0)
        else:  # MAIN
            try:
                server = Server()
                asyncio.run(server.start(host, port))
            except ConnectionError:  # some unrecoverable error or segfault, so restart the server
                exit(1)
