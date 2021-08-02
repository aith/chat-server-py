#!/usr/bin/env python3.8

import sys
import socket, threading

if __name__ == '__main__':
    port = 0
    try:
        port = int(sys.argv[1])
    except:
        print("Input a port number")
        exit(1)
    try:
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.connect(('127.0.0.1', port))
        nickname = input("Choose your nickname: ")
    except:
        print("Could not establissh connection to host on that port. ")
        exit(1)

def receive():
    while True:                                                 #making valid connection
        try:
            message = client.recv(1024).decode('ascii')
            if message == 'NICKNAME':
                client.send(nickname.encode('ascii'))
            else:
                print(message)
        except:                                                 #case on wrong ip/port details
            print("An error occured!")
            client.close()
            break
def write():
    while True:                                                 #message layout
        message = '{}: {}'.format(nickname, input(''))
        client.send(message.encode('ascii'))

receive_thread = threading.Thread(target=receive)               #receiving multiple messages
receive_thread.start()
write_thread = threading.Thread(target=write)                   #sending messages
write_thread.start()