"""Static internal DNS. No recursion, forwarding, query logs or external DNS."""
import ipaddress
import json
from pathlib import Path
import socketserver
import struct
import threading

def answer(packet,records):
    if len(packet)<12:return b''
    identifier,flags,questions,_,_,_=struct.unpack('!6H',packet[:12])
    if questions!=1 or flags&0x8000:return struct.pack('!6H',identifier,0x8401,0,0,0,0)
    labels=[];offset=12
    try:
        while True:
            size=packet[offset];offset+=1
            if size==0:break
            if size>63 or offset+size>len(packet) or offset>266:raise ValueError()
            label=packet[offset:offset+size].decode('ascii');offset+=size
            if not all(c.isalnum() or c in '_-' for c in label):raise ValueError()
            labels.append(label.lower())
        kind,cls=struct.unpack('!HH',packet[offset:offset+4]);offset+=4
        if cls!=1:raise ValueError()
    except (ValueError,IndexError,UnicodeError,struct.error):return struct.pack('!6H',identifier,0x8401,0,0,0,0)
    name='.'.join(labels);question=packet[12:offset]
    allowed=name in records
    count=int(allowed and kind==1)
    header=struct.pack('!6H',identifier,0x8400|(flags&0x0100)|(0 if allowed else 5),1,count,0,0)
    if not count:return header+question
    value=ipaddress.IPv4Address(records[name]).packed
    return header+question+b'\xc0\x0c'+struct.pack('!HHIH',1,1,30,4)+value

class UDP(socketserver.BaseRequestHandler):
    def handle(self):
        packet,channel=self.request;response=answer(packet,self.server.records)
        if response:channel.sendto(response,self.client_address)

class TCP(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(3)
        def exact(size):
            data=b''
            while len(data)<size:
                block=self.request.recv(size-len(data))
                if not block:raise ValueError()
                data+=block
            return data
        try:
            size=struct.unpack('!H',exact(2))[0]
            if not 12<=size<=4096:return
            data=answer(exact(size),self.server.records)
            if data:self.request.sendall(struct.pack('!H',len(data))+data)
        except (ValueError,OSError):pass

if __name__=='__main__':
    records=json.loads(Path('/dns/records.json').read_text())
    udp=socketserver.UDPServer(('0.0.0.0',5353),UDP);udp.records=records
    tcp=socketserver.TCPServer(('0.0.0.0',5353),TCP);tcp.records=records
    threading.Thread(target=tcp.serve_forever,daemon=True).start();udp.serve_forever()
