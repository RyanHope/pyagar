from struct import pack, unpack

def from_bytes (data, big_endian = False):
    if isinstance(data, str):
        data = bytearray(data)
    if big_endian:
        data = reversed(data)
    num = 0
    for offset, byte in enumerate(data):
        num += byte << (offset * 8)
    return num

class Buffer(object):

    def __init__(self, input=bytearray(), output=bytearray()):
        self.input = input
        self.output = output

    def read_string(self):
        string = ''
        while True:
            if len(self.input) < 2:
                break

            charBytes = self.input[:2]
            self.input = self.input[2:]

            charCode = from_bytes(charBytes)

            if charCode == 0:
                break

            char = charBytes.decode('utf-16')#chr(charCode)
            string += char
        return string

    def write_string(self, value):
        codes = [ord(char) for char in value]
        self.output += pack('<B ' + str(len(codes)) + 'H', 0, *codes)

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

    def read_int(self):
        value, = unpack('<I', self.input[:4])
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
        self.output = []
        return tmp

    def fill_session(self, session):
        self.input = session.read()

    def flush_session(self, session):
        session.write(self.output)
        self.output = []

    def input_size(self):
        return len(self.input)

    def output_size(self):
        return len(self.output)
