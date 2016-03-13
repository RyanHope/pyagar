__author__ = 'RAEON'

from struct import pack, unpack

class Buffer(object):

    def __init__(self, input=bytearray(), output=bytearray()):
        self.input = input
        self.output = output

    def read_string16(self):
        string = []
        while True:
            if len(self.input) < 2:
                break
            charCode = self.read_short()
            if charCode == 0:
                break
            string.append(unichr(charCode))
        return ''.join(string)

    def read_string8(self):
        string = []
        while True:
            if len(self.input) < 1:
                break
            charCode = self.read_byte()
            if charCode == 0:
                break
            string.append(chr(charCode))
        return ''.join(string)

    def write_string(self, value):
        self.output += pack('<B%iB' % (len(value)-1), *map(ord, value))

    def read_byte(self):
        value, = unpack('<B', self.input[:1])
        self.input = self.input[1:]
        return value

    def write_byte(self, value):
        self.output += pack('<B', value)

    def read_short(self):
        value, = unpack('<H', self.input[:2])
        self.input = self.input[2:]
        return value

    def write_short(self, value):
        self.output += pack('<H', value)

    def read_uint(self):
        value, = unpack('<I', self.input[:4])
        self.input = self.input[4:]
        return value

    def read_int(self):
        value, = unpack('<i', self.input[:4])
        self.input = self.input[4:]
        return value

    def write_int(self, value):
        self.output += pack('<I', value)

    def read_float(self):
        value, = unpack('<f', self.input[:4])
        self.input = self.input[4:]
        return value

    def write_float(self, value):
        self.output += pack('<f', value)

    def read_double(self):
        value, = unpack('<d', self.input[:8])
        self.input = self.input[8:]
        return value

    def write_double(self, value):
        self.output += pack('<d', value)

    def skip(self, value):
        self.input = self.input[value:]

    def fill(self, data):
        self.input = data

    def flush(self):
        tmp = self.output
        self.output = bytearray()
        return bytes(tmp)

    def flush_protocol(self, protocol):
        protocol.sendMessage(bytes(self.output), isBinary=True)
        self.output = bytearray()

    def input_size(self):
        return len(self.input)

    def output_size(self):
        return len(self.output)
